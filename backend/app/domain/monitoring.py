from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import (
    Agent,
    AgentStatus,
    AuditEvent,
    BudgetAccount,
    BudgetPolicy,
    PolicyScope,
    UsageRecord,
)


async def spend_summary(
    db: AsyncSession,
    *,
    entity_id: str,
    scope: PolicyScope | None = None,
    now: datetime | None = None,
) -> dict:
    account = await db.get(BudgetAccount, entity_id)
    if not account:
        return {
            "entity_id": entity_id, "scope": scope, "budget_limit": Decimal("0"),
            "settled_spend": Decimal("0"), "reserved_amount": Decimal("0"),
            "available": Decimal("0"), "utilization_pct": Decimal("0"),
            "rolling_60m_spend": Decimal("0"),
        }
    at = now or datetime.now(timezone.utc)
    since = at - timedelta(minutes=settings.RUNAWAY_WINDOW_MINUTES)
    entity_column = {
        PolicyScope.TEAM: UsageRecord.team_id,
        PolicyScope.AGENT: UsageRecord.agent_id,
        PolicyScope.SESSION: UsageRecord.session_id,
    }.get(scope, UsageRecord.agent_id)
    rolling = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.actual_cost), 0)).where(
            entity_column == entity_id, UsageRecord.created_at >= since
        )
    )
    return {
        "entity_id": entity_id, "scope": scope,
        "budget_limit": account.budget_limit, "settled_spend": account.settled_spend,
        "reserved_amount": account.reserved_amount, "available": account.available,
        "utilization_pct": account.utilization_pct,
        "rolling_60m_spend": Decimal(rolling or 0),
    }


async def usage_history(
    db: AsyncSession, *, entity_id: str | None = None, limit: int = 100
) -> list[UsageRecord]:
    stmt = select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(limit)
    if entity_id:
        stmt = stmt.where(
            (UsageRecord.team_id == entity_id)
            | (UsageRecord.agent_id == entity_id)
            | (UsageRecord.session_id == entity_id)
        )
    return list((await db.execute(stmt)).scalars().all())


async def audit_history(db: AsyncSession, *, agent_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if agent_id:
        stmt = stmt.where(AuditEvent.agent_id == agent_id)
    return list((await db.execute(stmt)).scalars().all())


async def set_agent_status(db: AsyncSession, agent_id: str, status: AgentStatus, reason: str) -> Agent:
    agent = await db.get(Agent, agent_id, with_for_update=True)
    if not agent:
        raise LookupError(agent_id)
    previous = agent.status
    agent.status = status
    db.add(AuditEvent(
        id=f"audit-{uuid4().hex}", event_type=f"AGENT_{status.value}",
        agent_id=agent.id, team_id=agent.team_id,
        details={"previous_status": previous.value, "reason": reason},
    ))
    await db.commit()
    await db.refresh(agent)
    return agent


async def detect_and_pause_runaway_agents(db: AsyncSession, *, now: datetime | None = None) -> list[str]:
    at = now or datetime.now(timezone.utc)
    since = at - timedelta(minutes=settings.RUNAWAY_WINDOW_MINUTES)
    result = await db.execute(select(Agent).where(Agent.status == AgentStatus.ACTIVE))
    paused: list[str] = []
    threshold_fraction = Decimal(settings.RUNAWAY_MONTHLY_BUDGET_PCT) / Decimal("100")
    for agent in result.scalars():
        policy = await db.scalar(select(BudgetPolicy).where(
            BudgetPolicy.scope == PolicyScope.AGENT, BudgetPolicy.agent_id == agent.id
        ))
        if not policy or policy.limit_amount <= 0:
            continue
        spend = await db.scalar(select(func.coalesce(func.sum(UsageRecord.actual_cost), 0)).where(
            UsageRecord.agent_id == agent.id, UsageRecord.created_at >= since
        ))
        if Decimal(spend or 0) < policy.limit_amount * threshold_fraction:
            continue
        await set_agent_status(
            db, agent.id, AgentStatus.PAUSED,
            f"rolling {settings.RUNAWAY_WINDOW_MINUTES}-minute spend exceeded "
            f"{settings.RUNAWAY_MONTHLY_BUDGET_PCT}% of monthly budget",
        )
        paused.append(agent.id)
    return paused
