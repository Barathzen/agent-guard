# AgentGuard --- Project Overview

**Full title:** Hierarchical Budget Enforcement and Runtime Governance
for Multi-Agent LLM Systems\
**Initial architecture:** FastAPI + PostgreSQL. Redis is intentionally
excluded.\
**Status:** Planning / Phase 0.

## 1. Summary

AgentGuard is an infrastructure-level budget controller between AI
agents and LLM providers. It intercepts requests, resolves
team/agent/session identity, checks spending policies, reserves
estimated cost before execution, records actual usage afterward, and
blocks or reroutes requests when required.

**Goal:** Prevent uncontrolled LLM spending before provider execution,
rather than merely reporting it after billing.

## 2. Problem statement

An enterprise runs multiple agents across teams. An agent can enter a
recursive loop and generate thousands of LLM calls. If enforcement
exists only in post-hoc billing reports, the organization discovers the
overspend after it has happened.

AgentGuard provides a controlled gateway through which supported agent
requests must pass before reaching an LLM provider.

## 3. Functional requirements

  -----------------------------------------------------------------------
  ID                      Requirement             Expected behavior
  ----------------------- ----------------------- -----------------------
  FR-01                   Team budget             Shared team limit and
                                                  time window

  FR-02                   Agent budget            Individual agent limit

  FR-03                   Session budget          Maximum spend per
                                                  session

  FR-04                   Metering                Record model, provider,
                                                  tokens, cost, and
                                                  request metadata

  FR-05                   Warning                 Warn at or above 80%
                                                  consumption

  FR-06                   Hard enforcement        Reject requests that
                                                  cannot fit within any
                                                  applicable budget

  FR-07                   Session closure         Close sessions when
                                                  their budget is
                                                  exhausted

  FR-08                   Model substitution      Select a cheaper
                                                  compatible model when a
                                                  model allocation is
                                                  exhausted

  FR-09                   Dashboard               Display spend, limits,
                                                  and request status

  FR-10                   Runaway detection       Flag and pause agents
                                                  consuming over 20% of
                                                  monthly budget in a
                                                  rolling hour
  -----------------------------------------------------------------------

## 4. Non-functional requirements

-   **Correctness:** Concurrent requests must not reserve more than the
    configured budget.
-   **Auditability:** Reservations, settlements, rejections, and
    adjustments are traceable.
-   **Reliability:** Failures and restarts must not silently lose
    reservations.
-   **Security:** Agent identity and provider credentials must not be
    trusted from arbitrary client fields.
-   **Observability:** Expose latency, provider failures, reservation
    failures, and budget decisions.
-   **Testability:** Core enforcement must work with a mock provider and
    no paid API.

## 5. Scope

### In scope

-   Team, agent, session, and optional model-level allocations.
-   Monthly and per-session budget windows.
-   Gateway interception and identity resolution.
-   Token metering and cost calculation.
-   Pre-request reservations and post-request settlement.
-   Atomic enforcement under concurrent requests.
-   Warnings, rejection, session closure, and model substitution.
-   Runaway-agent detection, human review, and dashboard.

### Out of scope for the first version

-   Multi-region deployment.
-   Enterprise billing integrations.
-   Automatic budget increases.
-   Guaranteed interception of agents with independent provider
    credentials.

**Security boundary:** AgentGuard only enforces requests routed through
it. Keep provider credentials behind the gateway and restrict direct
provider access in deployed environments where practical.

## 6. Architecture

``` mermaid
flowchart TD
    A[AI Agents] --> B[AgentGuard SDK / HTTP Client]
    B --> C[FastAPI LLM Gateway]
    C --> D[Authentication and Identity Resolver]
    D --> E[Budget Policy Engine]
    E --> F[PostgreSQL Transaction]
    F --> G{Reservation accepted?}
    G -- No --> H[Reject / Fallback Decision]
    G -- Yes --> I[Model Router]
    I --> J[Provider Adapter]
    J --> K[LLM Provider or Local Model]
    K --> L[Usage Metering]
    L --> M[Reservation Settlement]
    M --> F
    F --> N[Usage Ledger and Audit Events]
    N --> O[Monitoring API]
    O --> P[React Dashboard]
    N --> Q[Runaway Agent Detector]
    Q --> R[Pause and Human Review]
```

### Request lifecycle

1.  Agent sends a request to the gateway.
2.  Gateway authenticates the caller and resolves team, agent, and
    session identity.
3.  Gateway validates agent and session status.
4.  Token estimator calculates a conservative maximum request cost.
5.  Policy engine checks team, agent, session, and applicable model
    allocations.
6.  A database transaction atomically reserves the estimated amount.
7.  If reservation succeeds, the router selects the preferred or
    fallback model.
8.  Gateway calls the provider.
9.  Provider response and usage metadata are collected.
10. A settlement transaction records actual cost and releases unused
    reservation.
11. Usage events become available to monitoring and the dashboard.

## 7. Initial storage decision: PostgreSQL only

PostgreSQL is the only datastore in the first implementation.

It stores policies, budget accounts, reservations, sessions, pricing,
usage records, and audit events. We will use transactions, row-level
locks, conditional updates, constraints, and unique idempotency keys.

Redis is excluded initially. A separate in-memory store such as Valkey
can be evaluated later only if measurements justify it.

**Important:** Redis is not required to implement atomic budget
reservations. PostgreSQL can provide the initial correctness boundary.

## 8. Budget accounting model

For each budget account:

``` text
committed = settled_spend + active_reserved
available = budget_limit - committed
```

For estimated request cost `C`, reserve only if every applicable account
has enough available funds:

``` text
team_available   >= C
agent_available  >= C
session_available >= C
```

Lock all applicable account rows in a deterministic order and
check/reserve them in one transaction. Never keep a database transaction
open while waiting for an LLM response.

## 9. Cost model

For prices expressed per million tokens:

``` text
cost =
  (input_tokens * input_price_per_million
   + output_tokens * output_price_per_million)
  / 1_000_000
```

Use provider-reported token usage when available. Use a tokenizer-based
estimate when usage metadata is unavailable, and label it as estimated.
Use `Decimal` and PostgreSQL `NUMERIC` for monetary values, not binary
floating point.

Keep a pricing version or snapshot with each usage record so historical
costs remain explainable after prices change.

## 10. Enforcement policy

  Condition                      Action
  ------------------------------ ----------------------------------------
  Below 80%                      Allow if request fits
  At/above 80%, below 100%       Allow if request fits and emit warning
  Request would exceed a limit   Reject or attempt an allowed fallback
  Budget fully consumed          Reject new requests
  Session budget exhausted       Close session to new requests

Warnings should be idempotent per budget window or alert state, not
emitted on every subsequent request.

## 11. Model substitution

A cheaper model is not automatically equivalent. A fallback must: 1. Be
available and permitted by policy. 2. Support required capabilities. 3.
Satisfy context and output constraints. 4. Have a lower estimated cost
for this request. 5. Fit within every applicable budget. 6. Be recorded
with the substitution reason.

A model allocation is distinct from the total agent budget. If the
entire agent budget is exhausted, switching models cannot make the
request valid.

## 12. Runaway agent detection

Required rule:

``` text
spend_by_agent_in_rolling_60_minutes
    > 0.20 * agent_monthly_budget
```

When triggered, pause the agent for new gateway requests, create an
evidence-backed alert, preserve in-flight settlement, and require
authorized human review to resume it.

## 13. Technology stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Language                Python                  Core implementation

  API                     FastAPI                 Gateway and management
                                                  APIs

  ORM                     SQLAlchemy 2.x          Database mapping and
                                                  transactions

  Migrations              Alembic                 Schema evolution

  Database                PostgreSQL              Policies, reservations,
                                                  usage ledger

  Validation              Pydantic                Request/config
                                                  validation

  Token estimation        Provider tokenizer /    Preflight estimates
                          tiktoken where          
                          applicable              

  Local inference         Ollama (optional)       No-paid-API integration
                                                  testing

  Frontend                React + TypeScript      Dashboard

  Real-time               WebSockets or SSE       Dashboard updates

  Packaging               Docker Compose          Reproducible
                                                  environment

  Testing                 pytest                  Unit, integration,
                                                  concurrency tests
  -----------------------------------------------------------------------

Provider adapters must be separate from budget logic. LiteLLM may be
evaluated as an adapter, but enforcement must not depend on it.

## 14. Development phases

### Phase 0 --- Foundations and architecture

-   Finalize requirements, assumptions, and trust boundaries.
-   Define request lifecycle and system invariants.
-   Decide budget windows, reset, currency, and reservation semantics.
-   Define diagrams, repository structure, and local environment.
-   **Exit:** Architecture and invariants are documented and reviewed.

### Phase 1 --- Budget configuration

-   Design entities and relationships.
-   Implement teams, agents, sessions, budget policies, and model
    pricing.
-   Define budget periods, timezone, and policy update semantics.
-   Build CRUD/validation APIs, migrations, and tests.
-   **Exit:** Policies can be created, retrieved, updated, and
    validated.

### Phase 2 --- LLM gateway and interception

-   Define authenticated agent identity and request schemas.
-   Build FastAPI gateway and provider adapter interface.
-   Implement deterministic mock provider.
-   Route test-agent calls through the gateway.
-   **Exit:** Mock-provider integration works only through the gateway.

### Phase 3 --- Token metering and cost calculation

-   Estimate input tokens and reserve output allowance.
-   Parse provider-reported usage.
-   Implement pricing and cost calculation.
-   Persist request usage and handle missing usage metadata.
-   **Exit:** Cost calculations pass deterministic tests.

### Phase 4 --- Atomic budget enforcement

-   Define reservation state machine.
-   Lock all applicable budget rows consistently.
-   Reserve estimated maximum cost in one transaction.
-   Implement settlement, release, idempotency, and recovery.
-   Add warnings, hard blocks, and session closure.
-   **Exit:** Concurrency tests demonstrate no aggregate overspend.

### Phase 5 --- Intelligent model routing

-   Define model capabilities and fallback policy.
-   Add optional model-level allocation.
-   Filter compatible models and compare estimated cost.
-   Re-check all budgets for every candidate.
-   **Exit:** Only permitted, cheaper, compatible models that fit all
    budgets are selected.

### Phase 6 --- Monitoring and runaway detection

-   Build spend/utilization APIs and dashboard.
-   Add WebSocket or SSE updates.
-   Implement rolling 60-minute detector and 20% threshold.
-   Add pause, review, resume, and audit workflow.
-   **Exit:** Dashboard reconciles with ledger and runaway scenario
    pauses agent.

### Phase 7 --- Testing and hardening

-   Test concurrent agents and shared budgets.
-   Test provider timeouts, restarts, duplicate requests, and settlement
    retries.
-   Test database outage and fail-closed behavior.
-   Benchmark throughput, latency, and lock contention.
-   Document limitations and results.
-   **Exit:** Acceptance suite passes and measurements are documented.

## 15. Definition of done

-   Every supported LLM request passes through the gateway.
-   Team, agent, and session budgets are enforced.
-   Concurrent reservations are safe.
-   Usage is settled and auditable.
-   80% warnings and hard blocking work.
-   Session exhaustion closes the session to new requests.
-   Model substitution respects capabilities and all budgets.
-   Runaway detection pauses an agent for review.
-   Dashboard values reconcile with the ledger.
-   Tests cover concurrency and failure scenarios.
-   Setup and architecture documentation are reproducible.

## 16. Engineering invariants

1.  No provider call before successful reservation.
2.  Every applicable budget is checked atomically.
3.  Active reservations count against available budget.
4.  Every reservation is settled, released, or recoverable.
5.  Duplicate settlement cannot double-charge.
6.  No database transaction remains open during inference.
7.  Historical usage retains the pricing snapshot used.
8.  Fallback cannot bypass budget limits.
9.  Paused agents cannot make new gateway requests.
10. Derived counters can be reconciled against the durable ledger.

## 17. Reference topics

Study these as they appear in the phases: - ACID transactions and
isolation levels. - Row-level locks, deadlocks, and conditional
updates. - Idempotency keys and state machines. - Reservation/settlement
accounting. - Tokenization and model pricing. - Sliding-window
algorithms. - Provider adapters and routing policies. - WebSockets,
event-driven updates, fault injection, and load testing.

See `progress.md` for current status and `implementation.md` for the
execution checklist.
