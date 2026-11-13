from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from backend.app.core.config import settings
from backend.app.core.database import async_session_factory, engine
from backend.app.db.models import (
    Agent,
    AgentStatus,
    AuditEvent,
    BudgetAccount,
    BudgetPeriod,
    BudgetPolicy,
    BudgetWarningEvent,
    PolicyScope,
    Reservation,
    ReservationState,
    Session,
    SessionStatus,
    Team,
    UsageRecord,
)
from backend.app.domain.monitoring import detect_and_pause_runaway_agents, spend_summary
from backend.app.domain.reservation import (
    BudgetWarningService,
    InvalidStateTransitionError,
    ReservationRecoveryService,
    SessionExhaustionService,
    atomic_release,
    atomic_reserve,
    atomic_settle,
    mark_unknown,
)


@pytest_asyncio.fixture(autouse=True)
async def dispose_database_pool():
    yield
    await engine.dispose()


async def remove_rows(ids: list[str], policy_id: str | None = None) -> None:
    async with async_session_factory() as db:
        await db.execute(delete(UsageRecord).where(UsageRecord.request_id.like("phase7-%")))
        await db.execute(delete(AuditEvent).where(AuditEvent.id.like("audit-phase7-%")))
        await db.execute(delete(BudgetWarningEvent).where(BudgetWarningEvent.id.like("warning-phase7-%")))
        await db.execute(delete(Reservation).where(Reservation.id.like("phase7-%")))
        await db.execute(delete(BudgetAccount).where(BudgetAccount.id.in_(ids)))
        if policy_id:
            await db.execute(delete(BudgetPolicy).where(BudgetPolicy.id == policy_id))
        await db.execute(delete(Session).where(Session.id.in_(ids)))
        await db.execute(delete(Agent).where(Agent.id.in_(ids)))
        await db.execute(delete(Team).where(Team.id.in_(ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_concurrent_reservations_never_overspend_shared_account():
    account_id = "phase7-concurrency-account"
    await remove_rows([account_id])
    async with async_session_factory() as db:
        db.add(BudgetAccount(id=account_id, budget_limit=Decimal("1.000000")))
        await db.commit()

    async def reserve(index: int) -> bool:
        async with async_session_factory() as db:
            return await atomic_reserve(
                db,
                [account_id],
                Decimal("0.200000"),
                f"phase7-concurrency-{index}",
                "team",
                "agent",
                "session",
            )

    outcomes = await asyncio.gather(*(reserve(index) for index in range(10)))
    assert sum(outcomes) == 5

    async with async_session_factory() as db:
        account = await db.get(BudgetAccount, account_id)
        assert account is not None
        assert account.reserved_amount == Decimal("1.000000")
        await remove_rows([account_id])


@pytest.mark.asyncio
async def test_reservation_failure_transitions_and_settlement_are_idempotent():
    account_id = "phase7-transition-account"
    await remove_rows([account_id])
    async with async_session_factory() as db:
        db.add(BudgetAccount(id=account_id, budget_limit=Decimal("2.000000")))
        await db.commit()

        assert await atomic_reserve(
            db, [account_id], Decimal("1.000000"), "phase7-settle",
            "team", "agent", "session",
        )
        await atomic_settle(db, [account_id], Decimal("1.000000"), Decimal("0.400000"), "phase7-settle")
        await atomic_settle(db, [account_id], Decimal("1.000000"), Decimal("0.400000"), "phase7-settle")
        settled = await db.get(Reservation, "phase7-settle")
        assert settled is not None and settled.state == ReservationState.SETTLED

        assert await atomic_reserve(
            db, [account_id], Decimal("1.000000"), "phase7-release",
            "team", "agent", "session",
        )
        await atomic_release(db, [account_id], Decimal("1.000000"), "phase7-release")
        released = await db.get(Reservation, "phase7-release")
        assert released is not None and released.state == ReservationState.RELEASED

        assert await atomic_reserve(
            db, [account_id], Decimal("1.000000"), "phase7-unknown",
            "team", "agent", "session",
        )
        await mark_unknown(db, "phase7-unknown")
        unknown = await db.get(Reservation, "phase7-unknown")
        assert unknown is not None and unknown.state == ReservationState.UNKNOWN
        assert unknown.actual_cost == Decimal("0.000000")
        with pytest.raises(InvalidStateTransitionError):
            await atomic_release(db, [account_id], Decimal("1.000000"), "phase7-unknown")
    await remove_rows([account_id])


@pytest.mark.asyncio
async def test_stale_recovery_and_warning_boundary_are_deterministic():
    team_id, agent_id, session_id, policy_id = (
        "phase7-team", "phase7-agent", "phase7-session", "phase7-policy"
    )
    await remove_rows([team_id, agent_id, session_id], policy_id)
    async with async_session_factory() as db:
        db.add(Team(id=team_id, name="Phase 7"))
        await db.flush()
        db.add(Agent(id=agent_id, team_id=team_id, name="Phase 7 agent"))
        await db.flush()
        db.add(Session(id=session_id, agent_id=agent_id))
        await db.flush()
        db.add(BudgetPolicy(
            id=policy_id, scope=PolicyScope.SESSION,
            period=BudgetPeriod.SESSION_LIFETIME, limit_amount=Decimal("1"),
            session_id=session_id, warning_threshold_pct=80,
        ))
        await db.flush()
        db.add(BudgetAccount(
            id=session_id, policy_id=policy_id, budget_limit=Decimal("1"),
            settled_spend=Decimal("0.8"),
        ))
        await db.commit()
        assert await atomic_reserve(
            db, [session_id], Decimal("0.2"), "phase7-recovery",
            team_id, agent_id, session_id,
        )
        warnings = await BudgetWarningService().check_and_emit(db, [session_id], session_id)
        assert len(warnings) == 1
        assert await BudgetWarningService().check_and_emit(db, [session_id], session_id) == []

        reservation = await db.get(Reservation, "phase7-recovery")
        assert reservation is not None
        reservation.created_at = datetime.now(timezone.utc) - timedelta(minutes=61)
        await db.commit()
        assert await ReservationRecoveryService().recover_stale(db, 60) == ["phase7-recovery"]
        recovered = await db.get(Reservation, "phase7-recovery")
        assert recovered is not None and recovered.state == ReservationState.UNKNOWN
        await remove_rows([team_id, agent_id, session_id], policy_id)


@pytest.mark.asyncio
async def test_session_exhaustion_and_rolling_window_boundary():
    team_id, agent_id, session_id, policy_id = (
        "phase7-mon-team", "phase7-mon-agent", "phase7-mon-session", "phase7-mon-policy"
    )
    await remove_rows([team_id, agent_id, session_id], policy_id)
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        db.add(Team(id=team_id, name="Monitoring"))
        await db.flush()
        db.add(Agent(id=agent_id, team_id=team_id, name="Monitored agent"))
        await db.flush()
        db.add(Session(id=session_id, agent_id=agent_id))
        await db.flush()
        db.add(BudgetPolicy(
            id=policy_id, scope=PolicyScope.AGENT,
            period=BudgetPeriod.MONTHLY, limit_amount=Decimal("1"),
            agent_id=agent_id,
        ))
        await db.flush()
        db.add(BudgetAccount(id=agent_id, policy_id=policy_id, budget_limit=Decimal("1")))
        db.add(BudgetAccount(id=session_id, budget_limit=Decimal("1"), settled_spend=Decimal("1")))
        db.add_all([
            UsageRecord(
                id="phase7-window-in", request_id="phase7-window-in",
                team_id=team_id, agent_id=agent_id, session_id=session_id,
                provider="mock", model_name="mock", pricing_version="v1",
                currency="USD", estimated_input_tokens=1, estimated_output_tokens=1,
                actual_input_tokens=1, actual_output_tokens=1,
                estimated_cost=Decimal(".2"), actual_cost=Decimal(".2"),
                created_at=now - timedelta(minutes=59),
            ),
            UsageRecord(
                id="phase7-window-out", request_id="phase7-window-out",
                team_id=team_id, agent_id=agent_id, session_id=session_id,
                provider="mock", model_name="mock", pricing_version="v1",
                currency="USD", estimated_input_tokens=1, estimated_output_tokens=1,
                actual_input_tokens=1, actual_output_tokens=1,
                estimated_cost=Decimal(".3"), actual_cost=Decimal(".3"),
                created_at=now - timedelta(minutes=61),
            ),
        ])
        await db.commit()
        summary = await spend_summary(db, entity_id=agent_id, scope=PolicyScope.AGENT, now=now)
        assert summary["rolling_60m_spend"] == Decimal(".2")
        paused = await detect_and_pause_runaway_agents(db, now=now)
        assert paused == [agent_id]
        agent = await db.get(Agent, agent_id)
        assert agent is not None and agent.status == AgentStatus.PAUSED
        assert await SessionExhaustionService().check_and_close(db, session_id)
        session = await db.get(Session, session_id)
        assert session is not None and session.status == SessionStatus.EXHAUSTED
    await remove_rows([team_id, agent_id, session_id], policy_id)
