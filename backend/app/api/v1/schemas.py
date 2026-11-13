from decimal import Decimal
from typing import Any, Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from backend.app.db.models import PolicyScope, BudgetPeriod, AgentStatus, SessionStatus

# Team Schemas
class TeamCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)

class TeamOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

# Agent Schemas
class AgentCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)

class AgentOut(BaseModel):
    id: str
    team_id: str
    name: str
    status: AgentStatus
    created_at: datetime

    class Config:
        from_attributes = True

# Session Schemas
class SessionCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)

class SessionOut(BaseModel):
    id: str
    agent_id: str
    status: SessionStatus
    created_at: datetime

    class Config:
        from_attributes = True

# Budget Policy Schemas
class BudgetPolicyCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    scope: PolicyScope
    period: BudgetPeriod
    limit_amount: Decimal = Field(..., ge=Decimal("0.000000"))
    warning_threshold_pct: int = Field(default=80, ge=1, le=100)
    team_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_scope_target(self):
        if self.scope == PolicyScope.TEAM and not self.team_id:
            raise ValueError("team_id is required when scope is TEAM")
        if self.scope == PolicyScope.AGENT and not self.agent_id:
            raise ValueError("agent_id is required when scope is AGENT")
        if self.scope == PolicyScope.SESSION and not self.session_id:
            raise ValueError("session_id is required when scope is SESSION")
        return self

class BudgetPolicyUpdate(BaseModel):
    limit_amount: Optional[Decimal] = Field(None, ge=Decimal("0.000000"))
    warning_threshold_pct: Optional[int] = Field(None, ge=1, le=100)

class BudgetPolicyOut(BaseModel):
    id: str
    scope: PolicyScope
    period: BudgetPeriod
    limit_amount: Decimal
    warning_threshold_pct: int
    team_id: Optional[str]
    agent_id: Optional[str]
    session_id: Optional[str]

    class Config:
        from_attributes = True

class BudgetSummaryOut(BaseModel):
    entity_id: str
    scope: PolicyScope
    budget_limit: Decimal
    settled_spend: Decimal
    reserved_amount: Decimal
    available: Decimal


class SpendSummaryOut(BaseModel):
    entity_id: str
    scope: Optional[PolicyScope] = None
    budget_limit: Decimal = Decimal("0")
    settled_spend: Decimal = Decimal("0")
    reserved_amount: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    utilization_pct: Decimal = Decimal("0")
    rolling_60m_spend: Decimal = Decimal("0")


class UsageHistoryOut(BaseModel):
    request_id: str
    agent_id: str
    session_id: str
    model_name: str
    actual_cost: Decimal
    actual_input_tokens: int
    actual_output_tokens: int
    created_at: datetime


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    agent_id: Optional[str]
    team_id: Optional[str]
    details: Dict[str, Any]
    created_at: datetime


class ModelCapabilityCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=96)
    provider: str
    model_name: str
    available: bool = True
    max_context_tokens: int = Field(default=128000, gt=0)
    capabilities: List[str] = Field(default_factory=list)


class ModelRoutePolicyCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=64)
    agent_id: str
    preferred_model: str
    allowed_models: List[str] = Field(default_factory=list)
    fallback_models: List[str] = Field(default_factory=list)


class ModelAllocationCreate(BaseModel):
    id: str = Field(..., min_length=2, max_length=96)
    agent_id: str
    model_name: str
    allocation_limit: Decimal = Field(..., ge=Decimal("0.000000"))

# Add to backend/app/api/v1/schemas.py

class GatewayChatRequest(BaseModel):
    request_id: str = Field(..., description="Unique client-provided idempotency key")
    team_id: str
    agent_id: str
    session_id: str
    model: str = "mock-gpt-4o"
    messages: List[Dict[str, str]] = Field(..., min_length=1)
    max_output_tokens: int = Field(default=500, gt=0)
    simulate_error: Optional[str] = Field(None, description="'timeout' or 'provider_error' for failure testing")
    required_capabilities: List[str] = Field(default_factory=list)

class GatewayChatResponse(BaseModel):
    request_id: str
    reservation_id: str
    requested_model: str
    agent_id: str
    session_id: str
    model: str
    substitution_reason: Optional[str] = None
    content: str
    estimated_input_tokens: int
    actual_input_tokens: int
    actual_output_tokens: int
    estimated_cost: Decimal
    actual_cost: Decimal
    pricing_version: str
    currency: str
    latency_ms: float
    status: str = "SUCCESS"