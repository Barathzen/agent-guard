from decimal import Decimal
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import BudgetAccount, Reservation, ReservationState

async def atomic_reserve(
    session: AsyncSession,
    account_ids: List[str],
    estimated_cost: Decimal,
    request_id: str,
    team_id: str,
    agent_id: str,
    session_id: str
) -> bool:
    # Deterministic alphabetical ordering prevents deadlocks across concurrent requests
    sorted_ids = sorted(account_ids)
    stmt = (
        select(BudgetAccount)
        .where(BudgetAccount.id.in_(sorted_ids))
        .with_for_update()
        .order_by(BudgetAccount.id)
    )
    result = await session.execute(stmt)
    accounts = result.scalars().all()

    if len(accounts) != len(sorted_ids):
        return False

    for acc in accounts:
        if acc.available < estimated_cost:
            return False

    for acc in accounts:
        acc.reserved_amount += estimated_cost

    res = Reservation(
        id=request_id,
        team_id=team_id,
        agent_id=agent_id,
        session_id=session_id,
        estimated_cost=estimated_cost,
        state=ReservationState.RESERVED
    )
    session.add(res)
    await session.commit()
    return True

async def atomic_settle(
    session: AsyncSession,
    account_ids: List[str],
    estimated_cost: Decimal,
    actual_cost: Decimal,
    request_id: str
) -> None:
    sorted_ids = sorted(account_ids)
    stmt = (
        select(BudgetAccount)
        .where(BudgetAccount.id.in_(sorted_ids))
        .with_for_update()
        .order_by(BudgetAccount.id)
    )
    result = await session.execute(stmt)
    accounts = result.scalars().all()

    for acc in accounts:
        acc.reserved_amount -= estimated_cost
        acc.settled_spend += actual_cost

    res_stmt = select(Reservation).where(Reservation.id == request_id).with_for_update()
    res_result = await session.execute(res_stmt)
    reservation = res_result.scalar_one_or_none()
    if reservation:
        reservation.actual_cost = actual_cost
        reservation.state = ReservationState.SETTLED

    await session.commit()