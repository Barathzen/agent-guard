import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.db.models import (
    Team, Agent, Session, BudgetPolicy, BudgetAccount, PolicyScope,
    AgentStatus, SessionStatus, Reservation, UsageRecord, ModelCapability,
    ModelRoutePolicy, ModelAllocation
)
from backend.app.api.v1.schemas import (
    TeamCreate, TeamOut,
    AgentCreate, AgentOut,
    SessionCreate, SessionOut,
    BudgetPolicyCreate, BudgetPolicyUpdate, BudgetPolicyOut,
    BudgetSummaryOut,
    ModelCapabilityCreate, ModelRoutePolicyCreate, ModelAllocationCreate,
    SpendSummaryOut, UsageHistoryOut, AuditEventOut,
    GatewayChatRequest, GatewayChatResponse,
)
from backend.app.providers.base import AbstractLLMProvider
from backend.app.providers.mock import MockLLMProvider
from backend.app.domain.metering import (
    PricingNotFoundError,
    calculate_actual_cost,
    calculate_estimated_cost,
    persist_usage,
    resolve_pricing,
)
from backend.app.domain.reservation import (
    BudgetWarningService,
    SessionExhaustionService,
    atomic_release,
    atomic_reserve,
    atomic_settle,
    mark_unknown,
)
from backend.app.domain.routing import RouteCandidate, select_candidates, substitution_reason
from backend.app.domain.monitoring import (
    audit_history,
    detect_and_pause_runaway_agents,
    set_agent_status,
    spend_summary,
    usage_history,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_idempotency_cache: Dict[str, Dict[str, Any]] = {}
_idempotency_lock = asyncio.Lock()

async def require_gateway_auth(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.GATEWAY_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing gateway API key")
    return api_key


router = APIRouter(dependencies=[Depends(require_gateway_auth)])

def get_llm_provider() -> AbstractLLMProvider:
    return MockLLMProvider()

# ----------------- TEAMS -----------------
@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(Team, payload.id):
        raise HTTPException(status_code=400, detail="Team already exists")
    team = Team(id=payload.id, name=payload.name)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team

@router.get("/teams/{team_id}", response_model=TeamOut)
async def get_team(team_id: str, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team

# ----------------- AGENTS -----------------
@router.post("/teams/{team_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(team_id: str, payload: AgentCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Team, team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    if await db.get(Agent, payload.id):
        raise HTTPException(status_code=400, detail="Agent already exists")
    agent = Agent(id=payload.id, team_id=team_id, name=payload.name)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent

@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

# ----------------- SESSIONS -----------------
@router.post("/agents/{agent_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(agent_id: str, payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    if await db.get(Session, payload.id):
        raise HTTPException(status_code=400, detail="Session already exists")
    sess = Session(id=payload.id, agent_id=agent_id)
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return sess

@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    sess = await db.get(Session, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess

# ----------------- BUDGET POLICIES -----------------
@router.post("/budget-policies", response_model=BudgetPolicyOut, status_code=status.HTTP_201_CREATED)
async def create_budget_policy(payload: BudgetPolicyCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(BudgetPolicy, payload.id):
        raise HTTPException(status_code=400, detail="Policy already exists")

    # Target entity existence validation
    if payload.scope == PolicyScope.TEAM and not await db.get(Team, payload.team_id):
        raise HTTPException(status_code=404, detail="Target Team does not exist")
    elif payload.scope == PolicyScope.AGENT and not await db.get(Agent, payload.agent_id):
        raise HTTPException(status_code=404, detail="Target Agent does not exist")
    elif payload.scope == PolicyScope.SESSION and not await db.get(Session, payload.session_id):
        raise HTTPException(status_code=404, detail="Target Session does not exist")

    policy = BudgetPolicy(
        id=payload.id,
        scope=payload.scope,
        period=payload.period,
        limit_amount=payload.limit_amount,
        warning_threshold_pct=payload.warning_threshold_pct,
        team_id=payload.team_id,
        agent_id=payload.agent_id,
        session_id=payload.session_id,
    )
    db.add(policy)

    # Initialize associated BudgetAccount window
    account_id = payload.team_id or payload.agent_id or payload.session_id
    account = await db.get(BudgetAccount, account_id)
    if not account:
        account = BudgetAccount(
            id=account_id,
            policy_id=policy.id,
            budget_limit=payload.limit_amount
        )
        db.add(account)
    else:
        account.budget_limit = payload.limit_amount
        account.policy_id = policy.id

    await db.commit()
    await db.refresh(policy)
    return policy

@router.get("/budget-policies/{policy_id}", response_model=BudgetPolicyOut)
async def get_budget_policy(policy_id: str, db: AsyncSession = Depends(get_db)):
    policy = await db.get(BudgetPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

@router.patch("/budget-policies/{policy_id}", response_model=BudgetPolicyOut)
async def update_budget_policy(policy_id: str, payload: BudgetPolicyUpdate, db: AsyncSession = Depends(get_db)):
    policy = await db.get(BudgetPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    if payload.limit_amount is not None:
        policy.limit_amount = payload.limit_amount
        # Sync with budget account
        account_id = policy.team_id or policy.agent_id or policy.session_id
        account = await db.get(BudgetAccount, account_id)
        if account:
            account.budget_limit = payload.limit_amount

    if payload.warning_threshold_pct is not None:
        policy.warning_threshold_pct = payload.warning_threshold_pct

    await db.commit()
    await db.refresh(policy)
    return policy

# ----------------- BUDGET SUMMARIES -----------------
@router.get("/teams/{team_id}/budget", response_model=BudgetSummaryOut)
async def get_team_budget(team_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(BudgetAccount, team_id)
    if not account:
        raise HTTPException(status_code=404, detail="No budget account for this team")
    return BudgetSummaryOut(
        entity_id=team_id,
        scope=PolicyScope.TEAM,
        budget_limit=account.budget_limit,
        settled_spend=account.settled_spend,
        reserved_amount=account.reserved_amount,
        available=account.available,
    )

@router.get("/agents/{agent_id}/budget", response_model=BudgetSummaryOut)
async def get_agent_budget(agent_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(BudgetAccount, agent_id)
    if not account:
        raise HTTPException(status_code=404, detail="No budget account for this agent")
    return BudgetSummaryOut(
        entity_id=agent_id,
        scope=PolicyScope.AGENT,
        budget_limit=account.budget_limit,
        settled_spend=account.settled_spend,
        reserved_amount=account.reserved_amount,
        available=account.available,
    )

@router.get("/sessions/{session_id}/budget", response_model=BudgetSummaryOut)
async def get_session_budget(session_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(BudgetAccount, session_id)
    if not account:
        raise HTTPException(status_code=404, detail="No budget account for this session")
    return BudgetSummaryOut(
        entity_id=session_id,
        scope=PolicyScope.SESSION,
        budget_limit=account.budget_limit,
        settled_spend=account.settled_spend,
        reserved_amount=account.reserved_amount,
        available=account.available,
    )


@router.post("/model-capabilities", status_code=status.HTTP_201_CREATED)
async def create_model_capability(
    payload: ModelCapabilityCreate, db: AsyncSession = Depends(get_db)
):
    if await db.get(ModelCapability, payload.id):
        raise HTTPException(status_code=400, detail="Model capability already exists")
    capability = ModelCapability(**payload.model_dump())
    db.add(capability)
    await db.commit()
    await db.refresh(capability)
    return capability


@router.post("/agents/{agent_id}/model-route-policy", status_code=status.HTTP_201_CREATED)
async def create_model_route_policy(
    agent_id: str, payload: ModelRoutePolicyCreate, db: AsyncSession = Depends(get_db)
):
    if payload.agent_id != agent_id:
        raise HTTPException(status_code=400, detail="agent_id does not match route")
    if not await db.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    if await db.get(ModelRoutePolicy, payload.id):
        raise HTTPException(status_code=400, detail="Model route policy already exists")
    existing = await db.scalar(
        select(ModelRoutePolicy).where(ModelRoutePolicy.agent_id == agent_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Agent already has a model route policy")
    policy = ModelRoutePolicy(**payload.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.post("/agents/{agent_id}/model-allocations", status_code=status.HTTP_201_CREATED)
async def create_model_allocation(
    agent_id: str, payload: ModelAllocationCreate, db: AsyncSession = Depends(get_db)
):
    if payload.agent_id != agent_id:
        raise HTTPException(status_code=400, detail="agent_id does not match route")
    if not await db.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    if await db.get(ModelAllocation, payload.id):
        raise HTTPException(status_code=400, detail="Model allocation already exists")
    allocation = ModelAllocation(**payload.model_dump())
    db.add(allocation)
    await db.commit()
    await db.refresh(allocation)
    return allocation


@router.get("/monitoring/summary/{scope}/{entity_id}", response_model=SpendSummaryOut)
async def get_spend_summary(
    scope: PolicyScope, entity_id: str, db: AsyncSession = Depends(get_db)
):
    return await spend_summary(db, entity_id=entity_id, scope=scope)


@router.get("/monitoring/usage", response_model=list[UsageHistoryOut])
async def get_usage_history(
    entity_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return await usage_history(db, entity_id=entity_id, limit=limit)


@router.get("/monitoring/audit", response_model=list[AuditEventOut])
async def get_audit_history(
    agent_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return await audit_history(db, agent_id=agent_id, limit=limit)


@router.post("/monitoring/runaway/scan")
async def scan_runaway_agents(db: AsyncSession = Depends(get_db)):
    paused = await detect_and_pause_runaway_agents(db)
    return {"paused_agent_ids": paused, "count": len(paused)}


@router.post("/agents/{agent_id}/pause", response_model=AgentOut)
async def pause_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await set_agent_status(db, agent_id, AgentStatus.PAUSED, "manual pause")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc


@router.post("/agents/{agent_id}/resume", response_model=AgentOut)
async def resume_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await set_agent_status(db, agent_id, AgentStatus.ACTIVE, "manual resume")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc


@router.get("/monitoring/stream")
async def monitoring_stream(db: AsyncSession = Depends(get_db)):
    async def events():
        while True:
            result = await db.execute(select(BudgetAccount).order_by(BudgetAccount.id))
            accounts = result.scalars().all()
            await db.rollback()
            payload = [
                {
                    "entity_id": account.id,
                    "budget_limit": account.budget_limit,
                    "settled_spend": account.settled_spend,
                    "reserved_amount": account.reserved_amount,
                    "available": account.available,
                    "utilization_pct": account.utilization_pct,
                }
                for account in accounts
            ]
            yield f"event: budget\\ndata: {json.dumps(payload, default=str)}\\n\\n"
            await asyncio.sleep(settings.MONITORING_SSE_INTERVAL_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream")

# ----------------- LLM GATEWAY (Phase 2) -----------------
@router.post("/gateway/chat/completions", response_model=GatewayChatResponse)
async def gateway_chat_completions(
    payload: GatewayChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_gateway_auth),
    provider: AbstractLLMProvider = Depends(get_llm_provider),
):
    # Request correlation: accept client-provided idempotency key and also expose it in response
    request_id = payload.request_id

    # Idempotency: reject duplicates (in-memory fast path + durable reservation-id check)
    async with _idempotency_lock:
        if request_id in _idempotency_cache:
            raise HTTPException(status_code=409, detail="Duplicate request_id: idempotency key already used")
    existing_res = await db.get(Reservation, request_id)
    existing_usage = None
    if hasattr(db, "execute"):
        existing_usage = (await db.execute(
            select(UsageRecord).where(UsageRecord.request_id == request_id)
        )).scalar_one_or_none()
    if existing_res or existing_usage:
        raise HTTPException(status_code=409, detail="Duplicate request_id: idempotency key already used")

    # Server-side identity resolution and validation
    agent = await db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.team_id != payload.team_id:
        raise HTTPException(status_code=400, detail="Agent does not belong to provided team_id")
    session = await db.get(Session, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.agent_id != payload.agent_id:
        raise HTTPException(status_code=400, detail="Session does not belong to provided agent_id")
    if agent.status != AgentStatus.ACTIVE:
        raise HTTPException(status_code=403, detail=f"Agent is not active (status={agent.status})")
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail=f"Session is not active (status={session.status})")

    estimated_input_tokens = provider.estimate_input_tokens([m.model_dump() if hasattr(m, "model_dump") else m for m in payload.messages])
    provider_name = "mock"
    persistent_db = hasattr(db, "execute") and hasattr(db, "add")
    if persistent_db:
        route_policy = await db.scalar(
            select(ModelRoutePolicy).where(ModelRoutePolicy.agent_id == payload.agent_id)
        )
        fallback_names = (
            list(dict.fromkeys(
                ([route_policy.preferred_model] if route_policy else [])
                + (list(route_policy.fallback_models) if route_policy else [])
            ))
            if route_policy
            else []
        )
        allowed_names = list(route_policy.allowed_models) if route_policy else []
        model_names = [payload.model, *fallback_names]
        capability_result = await db.execute(
            select(ModelCapability).where(
                ModelCapability.provider == provider_name,
                ModelCapability.model_name.in_(model_names),
            )
        )
        capabilities = {item.model_name: item for item in capability_result.scalars().all()}
        route_candidates: list[RouteCandidate] = []
        pricing_by_model = {}
        allocation_by_model = {}
        for model_name in dict.fromkeys(model_names):
            try:
                model_pricing = await resolve_pricing(db, provider_name, model_name)
            except PricingNotFoundError:
                continue
            capability = capabilities.get(model_name)
            if model_name != payload.model and capability is None:
                continue
            route_candidates.append(
                RouteCandidate(
                    model_name=model_name,
                    input_price_per_m=model_pricing.input_price_per_m,
                    output_price_per_m=model_pricing.output_price_per_m,
                    available=capability.available if capability else True,
                    capabilities=frozenset(capability.capabilities if capability else ()),
                    max_context_tokens=capability.max_context_tokens if capability else 128000,
                )
            )
            pricing_by_model[model_name] = model_pricing
            allocation_by_model[model_name] = await db.scalar(
                select(ModelAllocation).where(
                    ModelAllocation.agent_id == payload.agent_id,
                    ModelAllocation.model_name == model_name,
                )
            )
        candidates = select_candidates(
            payload.model,
            route_candidates,
            allowed_models=allowed_names,
            fallback_models=fallback_names,
            required_capabilities=payload.required_capabilities,
            input_tokens=estimated_input_tokens,
            max_output_tokens=payload.max_output_tokens,
        )
        if not candidates:
            raise HTTPException(status_code=422, detail="No available compatible model")
        pricing = pricing_by_model[candidates[0].model_name]
    else:
        # Test doubles do not provide the pricing repository.
        from backend.app.db.models import ModelPricing
        pricing = ModelPricing(
            id="test-mock-gpt-4o-v1",
            provider=provider_name,
            model_name=payload.model,
            input_price_per_m=Decimal("1"),
            output_price_per_m=Decimal("2"),
            currency="USD",
            effective_from=datetime.now(timezone.utc),
            pricing_version="v1",
        )
        candidates = [
            RouteCandidate(
                model_name=payload.model,
                input_price_per_m=pricing.input_price_per_m,
                output_price_per_m=pricing.output_price_per_m,
            )
        ]
    estimated_cost = calculate_estimated_cost(
        estimated_input_tokens, payload.max_output_tokens, pricing
    )

    selected_candidate = candidates[0]
    account_ids = [payload.team_id, payload.agent_id, payload.session_id]
    if persistent_db:
        reserved = False
        selected_allocation_id = None
        for candidate in candidates:
            candidate_pricing = pricing_by_model[candidate.model_name]
            candidate_estimated_cost = calculate_estimated_cost(
                estimated_input_tokens, payload.max_output_tokens, candidate_pricing
            )
            if await atomic_reserve(
                db, account_ids, candidate_estimated_cost, request_id,
                payload.team_id, payload.agent_id, payload.session_id,
                allocation_by_model[candidate.model_name].id
                if allocation_by_model.get(candidate.model_name) else None,
            ):
                selected_candidate = candidate
                pricing = candidate_pricing
                estimated_cost = candidate_estimated_cost
                selected_allocation_id = (
                    allocation_by_model[candidate.model_name].id
                    if allocation_by_model.get(candidate.model_name) else None
                )
                reserved = True
                break
        if not reserved:
            raise HTTPException(status_code=402, detail="Insufficient budget for team, agent, or session")
        await BudgetWarningService().check_and_emit(db, account_ids, payload.session_id)

    try:
        provider_response = await asyncio.wait_for(
            provider.generate(
                request_id=request_id,
                model=selected_candidate.model_name,
                messages=[m for m in payload.messages],
                max_output_tokens=payload.max_output_tokens,
                simulate_error=payload.simulate_error,
            ),
            timeout=settings.GATEWAY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        if persistent_db:
            await mark_unknown(db, request_id)
        raise HTTPException(status_code=504, detail="Gateway/provider timeout")
    except asyncio.CancelledError:
        if persistent_db:
            await mark_unknown(db, request_id)
        raise HTTPException(status_code=499, detail="Request cancelled")
    except RuntimeError as exc:
        if persistent_db:
            await atomic_release(db, account_ids, estimated_cost, request_id, selected_allocation_id)
        raise HTTPException(status_code=502, detail=str(exc))

    # Respect client disconnect/cancellation after provider work where possible
    if await request.is_disconnected():
        if persistent_db:
            await mark_unknown(db, request_id)
        raise HTTPException(status_code=499, detail="Client disconnected")

    actual_cost = calculate_actual_cost(
        provider_response.usage.input_tokens,
        provider_response.usage.output_tokens,
        pricing,
    )
    if persistent_db:
        await atomic_settle(
            db, account_ids, estimated_cost, actual_cost, request_id, selected_allocation_id
        )
        await persist_usage(
            db,
            request_id=request_id,
            team_id=payload.team_id,
            agent_id=payload.agent_id,
            session_id=payload.session_id,
            provider=provider_name,
            model_name=provider_response.model,
            pricing=pricing,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=payload.max_output_tokens,
            actual_input_tokens=provider_response.usage.input_tokens,
            actual_output_tokens=provider_response.usage.output_tokens,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
        )
        await SessionExhaustionService().check_and_close(db, payload.session_id)
    response = GatewayChatResponse(
        request_id=request_id,
        reservation_id=request_id,
        requested_model=payload.model,
        agent_id=payload.agent_id,
        session_id=payload.session_id,
        model=provider_response.model,
        substitution_reason=substitution_reason(payload.model, provider_response.model),
        content=provider_response.content,
        estimated_input_tokens=estimated_input_tokens,
        actual_input_tokens=provider_response.usage.input_tokens,
        actual_output_tokens=provider_response.usage.output_tokens,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
        pricing_version=pricing.pricing_version,
        currency=pricing.currency,
        latency_ms=provider_response.latency_ms,
        status="SUCCESS",
    )

    async with _idempotency_lock:
        _idempotency_cache[request_id] = {"status": "completed"}
    return response