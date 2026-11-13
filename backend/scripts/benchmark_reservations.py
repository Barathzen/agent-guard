"""Measure PostgreSQL reservation latency and throughput.

The target database must already contain a budget account. The benchmark
uses a fresh request id for each operation and rolls back each reservation,
so it does not change settled spend.
"""
import asyncio
import statistics
import sys
import time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.domain.reservation import atomic_reserve, atomic_release


async def main(account_id: str, samples: int, concurrency: int) -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    successes = 0

    async def one() -> None:
        nonlocal successes
        async with semaphore:
            request_id = f"bench-{uuid4().hex}"
            started = time.perf_counter()
            async with factory() as db:
                ok = await atomic_reserve(
                    db, [account_id], Decimal("0.000001"), request_id,
                    account_id, account_id, account_id,
                )
                if ok:
                    await atomic_release(db, [account_id], Decimal("0.000001"), request_id)
                    successes += 1
            latencies.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(samples)))
    elapsed = time.perf_counter() - started
    await engine.dispose()
    print(f"samples={samples} concurrency={concurrency} successes={successes}")
    print(f"throughput={samples / elapsed:.2f} ops/s")
    print(
        "latency_ms "
        f"p50={statistics.median(latencies):.2f} "
        f"p95={statistics.quantiles(latencies, n=20)[18]:.2f} "
        f"max={max(latencies):.2f}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: benchmark_reservations.py ACCOUNT_ID SAMPLES CONCURRENCY")
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))
