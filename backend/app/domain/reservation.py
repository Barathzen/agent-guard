from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    BudgetAccount,
    BudgetPolicy,
    BudgetPeriod,
    BudgetWarningEvent,
    ModelAllocation,
    Reservation,
    ReservationState,
    Session,
    SessionStatus,
)


class ReservationNotFoundError(LookupError):
    pass


class InvalidStateTransitionError(RuntimeError):
    pass


def _account_ids(account_ids: Iterable[str]) -> list[str]:
    return sorted(set(account_ids))


async def _locked_accounts(db: AsyncSession, account_ids: Iterable[str]) -> list[BudgetAccount]:
    ids = _account_ids(account_ids)
    result = await db.execute(
        select(BudgetAccount)
        .where(BudgetAccount.id.in_(ids))
        .order_by(BudgetAccount.id)
        .with_for_update()
    )
    return list(result.scalars().all())


async def atomic_reserve(
    session: AsyncSession,
    account_ids: list[str],
    estimated_cost: Decimal,
    request_id: str,
    team_id: str,
    agent_id: str,
    session_id: str,
    model_allocation_id: str | None = None,
) -> bool:
    if estimated_cost < 0:
        raise ValueError("Estimated cost cannot be negative")
    accounts = await _locked_accounts(session, account_ids)
    ids = _account_ids(account_ids)
    if len(accounts) != len(ids) or any(account.available < estimated_cost for account in accounts):
        await session.rollback()
        return False
    allocation = None
    if model_allocation_id:
        allocation = await session.get(ModelAllocation, model_allocation_id, with_for_update=True)
        if allocation is None or allocation.available < estimated_cost:
            await session.rollback()
            return False
    existing = await session.get(Reservation, request_id, with_for_update=True)
    if existing is not None:
        await session.rollback()
        return False
    for account in accounts:
        account.reserved_amount += estimated_cost
    if allocation:
        allocation.reserved_amount += estimated_cost
    session.add(
        Reservation(
            id=request_id,
            team_id=team_id,
            agent_id=agent_id,
            session_id=session_id,
            model_allocation_id=model_allocation_id,
            estimated_cost=estimated_cost,
            state=ReservationState.RESERVED,
        )
    )
    await session.commit()
    return True


async def atomic_settle(
    session: AsyncSession,
    account_ids: list[str],
    estimated_cost: Decimal,
    actual_cost: Decimal,
    request_id: str,
    model_allocation_id: str | None = None,
) -> None:
    if actual_cost < 0:
        raise ValueError("Actual cost cannot be negative")
    reservation = await session.get(Reservation, request_id, with_for_update=True)
    if reservation is None:
        raise ReservationNotFoundError(request_id)
    if reservation.state == ReservationState.SETTLED:
        await session.rollback()
        return
    if reservation.state != ReservationState.RESERVED:
        state = reservation.state
        await session.rollback()
        raise InvalidStateTransitionError(f"{state} cannot transition to SETTLED")
    accounts = await _locked_accounts(session, account_ids)
    if len(accounts) != len(_account_ids(account_ids)):
        await session.rollback()
        raise ReservationNotFoundError("One or more budget accounts are missing")
    allocation = (
        await session.get(ModelAllocation, model_allocation_id, with_for_update=True)
        if model_allocation_id
        else None
    )
    if model_allocation_id and allocation is None:
        await session.rollback()
        raise ReservationNotFoundError("Model allocation is missing")
    for account in accounts:
        account.reserved_amount -= estimated_cost
        account.settled_spend += actual_cost
    if allocation:
        allocation.reserved_amount -= estimated_cost
        allocation.settled_spend += actual_cost
    reservation.actual_cost = actual_cost
    reservation.state = ReservationState.SETTLED
    await session.commit()


async def atomic_release(
    session: AsyncSession,
    account_ids: list[str],
    estimated_cost: Decimal,
    request_id: str,
    model_allocation_id: str | None = None,
) -> None:
    reservation = await session.get(Reservation, request_id, with_for_update=True)
    if reservation is None:
        raise ReservationNotFoundError(request_id)
    if reservation.state == ReservationState.RELEASED:
        await session.rollback()
        return
    if reservation.state != ReservationState.RESERVED:
        state = reservation.state
        await session.rollback()
        raise InvalidStateTransitionError(f"{state} cannot transition to RELEASED")
    accounts = await _locked_accounts(session, account_ids)
    if len(accounts) != len(_account_ids(account_ids)):
        await session.rollback()
        raise ReservationNotFoundError("One or more budget accounts are missing")
    allocation = (
        await session.get(ModelAllocation, model_allocation_id, with_for_update=True)
        if model_allocation_id
        else None
    )
    if model_allocation_id and allocation is None:
        await session.rollback()
        raise ReservationNotFoundError("Model allocation is missing")
    for account in accounts:
        account.reserved_amount -= estimated_cost
    if allocation:
        allocation.reserved_amount -= estimated_cost
    reservation.state = ReservationState.RELEASED
    await session.commit()


async def mark_unknown(session: AsyncSession, request_id: str) -> None:
    reservation = await session.get(Reservation, request_id, with_for_update=True)
    if reservation is None:
        raise ReservationNotFoundError(request_id)
    if reservation.state == ReservationState.UNKNOWN:
        await session.rollback()
        return
    if reservation.state != ReservationState.RESERVED:
        state = reservation.state
        await session.rollback()
        raise InvalidStateTransitionError(f"{state} cannot transition to UNKNOWN")
    reservation.state = ReservationState.UNKNOWN
    await session.commit()


class BudgetWarningService:
    async def check_and_emit(
        self, db: AsyncSession, account_ids: Iterable[str], session_id: str, at: datetime | None = None
    ) -> list[BudgetWarningEvent]:
        now = at or datetime.now(timezone.utc)
        accounts = await db.execute(
            select(BudgetAccount, BudgetPolicy)
            .join(BudgetPolicy, BudgetPolicy.id == BudgetAccount.policy_id)
            .where(BudgetAccount.id.in_(_account_ids(account_ids)))
        )
        events: list[BudgetWarningEvent] = []
        for account, policy in accounts.all():
            if account.budget_limit <= 0 or account.utilization_pct < Decimal(policy.warning_threshold_pct):
                continue
            if policy.period == BudgetPeriod.SESSION_LIFETIME:
                window_key = session_id
            elif policy.period == BudgetPeriod.MONTHLY:
                window_key = now.strftime("%Y-%m")
            else:
                window_key = now.strftime("%G-W%V")
            exists = await db.scalar(
                select(BudgetWarningEvent.id).where(
                    BudgetWarningEvent.account_id == account.id,
                    BudgetWarningEvent.window_key == window_key,
                )
            )
            if exists:
                continue
            event = BudgetWarningEvent(
                id=f"warning-{uuid4().hex}",
                account_id=account.id,
                threshold_pct=policy.warning_threshold_pct,
                utilization_pct=account.utilization_pct,
                window_key=window_key,
            )
            db.add(event)
            events.append(event)
        if events:
            await db.commit()
        return events


class SessionExhaustionService:
    async def check_and_close(self, db: AsyncSession, session_id: str) -> bool:
        budget = await db.get(BudgetAccount, session_id, with_for_update=True)
        session = await db.get(Session, session_id, with_for_update=True)
        if not budget or not session or budget.available > 0 or session.status != SessionStatus.ACTIVE:
            return False
        session.status = SessionStatus.EXHAUSTED
        await db.commit()
        return True


class ReservationRecoveryService:
    async def recover_stale(self, db: AsyncSession, staleness_minutes: int = 60) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=staleness_minutes)
        result = await db.execute(
            select(Reservation)
            .where(Reservation.state == ReservationState.RESERVED, Reservation.created_at < cutoff)
            .with_for_update()
        )
        reservations = list(result.scalars().all())
        ids = [reservation.id for reservation in reservations]
        for reservation in reservations:
            reservation.state = ReservationState.UNKNOWN
        if reservations:
            await db.commit()
        return ids
