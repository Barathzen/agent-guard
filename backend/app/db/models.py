import enum
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Numeric, DateTime, Enum, ForeignKey, CheckConstraint, UniqueConstraint
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

    model_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_price_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    output_price_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(32), default="v1")