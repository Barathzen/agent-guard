import enum
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Numeric, DateTime, Enum, ForeignKey, CheckConstraint, UniqueConstraint, JSON, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class PolicyScope(str, enum.Enum):
    TEAM = "TEAM"
    AGENT = "AGENT"
    SESSION = "SESSION"

class BudgetPeriod(str, enum.Enum):
    MONTHLY = "MONTHLY"
    ROLLING_30_DAYS = "ROLLING_30_DAYS"
    SESSION_LIFETIME = "SESSION_LIFETIME"

class AgentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"

class SessionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    CLOSED = "CLOSED"

class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agents: Mapped[List["Agent"]] = relationship("Agent", back_populates="team", cascade="all, delete-orphan")
    policies: Mapped[List["BudgetPolicy"]] = relationship("BudgetPolicy", back_populates="team")

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(64), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(Enum(AgentStatus), default=AgentStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    team: Mapped["Team"] = relationship("Team", back_populates="agents")
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="agent", cascade="all, delete-orphan")
    policies: Mapped[List["BudgetPolicy"]] = relationship("BudgetPolicy", back_populates="agent")

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="sessions")
    policies: Mapped[List["BudgetPolicy"]] = relationship("BudgetPolicy", back_populates="session")

class BudgetPolicy(Base):
    __tablename__ = "budget_policies"
    __table_args__ = (
        CheckConstraint("limit_amount >= 0", name="check_positive_limit"),
        CheckConstraint("warning_threshold_pct > 0 AND warning_threshold_pct <= 100", name="check_valid_threshold"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[PolicyScope] = mapped_column(Enum(PolicyScope), nullable=False)
    period: Mapped[BudgetPeriod] = mapped_column(Enum(BudgetPeriod), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    warning_threshold_pct: Mapped[int] = mapped_column(default=80)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    team_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True)

    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="policies")
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="policies")
    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="policies")

class BudgetAccount(Base):
    __tablename__ = "budget_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("budget_policies.id"), nullable=True)
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    settled_spend: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0.000000"))
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0.000000"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    @property
    def available(self) -> Decimal:
        return self.budget_limit - (self.settled_spend + self.reserved_amount)

    @property
    def committed(self) -> Decimal:
        return self.settled_spend + self.reserved_amount

    @property
    def utilization_pct(self) -> Decimal:
        if self.budget_limit == 0:
            return Decimal("100.00")
        return (self.committed / self.budget_limit * 100).quantize(Decimal("0.01"))

class ReservationState(str, enum.Enum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    UNKNOWN = "UNKNOWN"

class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0.000000"))
    state: Mapped[ReservationState] = mapped_column(Enum(ReservationState), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class ModelPricing(Base):
    __tablename__ = "model_pricings"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_price_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    output_price_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pricing_version: Mapped[str] = mapped_column(String(32), nullable=False)


class ModelCapability(Base):
    __tablename__ = "model_capabilities"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_model_capability_provider_name"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=128000, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ModelRoutePolicy(Base):
    __tablename__ = "model_route_policies"
    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_model_route_policy_agent"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    preferred_model: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    fallback_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_usage_records_request_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    estimated_input_tokens: Mapped[int] = mapped_column(nullable=False)
    estimated_output_tokens: Mapped[int] = mapped_column(nullable=False)
    actual_input_tokens: Mapped[int] = mapped_column(nullable=False)
    actual_output_tokens: Mapped[int] = mapped_column(nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class BudgetWarningEvent(Base):
    __tablename__ = "budget_warning_events"
    __table_args__ = (
        UniqueConstraint("account_id", "window_key", name="uq_budget_warning_account_window"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("budget_accounts.id", ondelete="CASCADE"), nullable=False
    )
    threshold_pct: Mapped[int] = mapped_column(nullable=False)
    utilization_pct: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    window_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)