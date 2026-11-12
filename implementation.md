# AgentGuard --- Implementation Guide

Follow this guide in order. Do not start a later phase until the current
phase's exit criteria are satisfied.

## 0. Working rules

1.  Understand the concept before implementation.
2.  Draw or update diagrams before complex modules.
3.  Implement a small vertical slice at a time.
4.  Add tests with each behavior.
5.  Run relevant tests before committing.
6.  Update `progress.md` after each work session.
7.  Record important design decisions and trade-offs.
8.  Never put provider credentials in frontend code or agent-visible
    configuration.

## 1. Suggested repository structure

``` text
agentguard/
├── README.md
├── project.md
├── progress.md
├── implementation.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
├── backend/
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   └── security.py
│       ├── api/v1/
│       │   ├── routes/
│       │   └── schemas/
│       ├── domain/
│       │   ├── budgets/
│       │   ├── agents/
│       │   ├── sessions/
│       │   ├── metering/
│       │   └── routing/
│       ├── services/
│       ├── providers/
│       │   ├── base.py
│       │   ├── mock.py
│       │   └── ollama.py
│       ├── repositories/
│       └── db/
│           ├── base.py
│           ├── models/
│           └── session.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── concurrency/
│   └── fixtures/
└── frontend/
```

Keep domain logic independent of FastAPI route handlers and provider
SDKs.

## 2. Local environment

Use a supported Python 3.11 or 3.12 release.

``` bash
mkdir agentguard
cd agentguard

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install fastapi uvicorn sqlalchemy alembic \
  "psycopg[binary]" pydantic pydantic-settings \
  pytest pytest-asyncio httpx
```

Pin tested versions in `pyproject.toml` after the environment is
verified.

Example local PostgreSQL setup (installed natively, no Docker):

``` bash
# Create the database (adjust for your local user/password)
createdb agentguard
```

Configure the connection via `.env` (copy from `.env.example`):

``` bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/agentguard
```

This is for local development only. Replace credentials and restrict
network access in deployed environments. Never commit real secrets.

## 3. Phase 0 --- Foundations

### Step 0.1: Write system invariants

-   No LLM call before reservation succeeds.
-   Team, agent, and session constraints are checked together.
-   Active reservations count against available budget.
-   A reservation cannot be settled twice.
-   Provider failures are reconciled.
-   No database transaction remains open during inference.
-   A paused agent cannot make new gateway requests.
-   Cost records identify the pricing version used.

### Step 0.2: Define budget semantics

Decide and document: - Currency and whether multiple currencies are
supported. - `NUMERIC` precision and rounding policy. - Calendar month
versus rolling 30-day period. - UTC storage and billing-window
timezone. - How a new budget period is created. - Whether active
reservations count against committed spend. - How actual cost above
reservation is handled. - How policy decreases affect active
reservations. - How ambiguous provider timeouts are reconciled.

### Step 0.3: Draw diagrams

Create: - Context diagram. - Component architecture. - Request sequence
diagram. - Budget entity relationship diagram. - Reservation state
machine.

Suggested reservation state machine:

``` mermaid
stateDiagram-v2
    [*] --> RESERVED
    RESERVED --> SETTLED: Provider usage received
    RESERVED --> RELEASED: Confirmed no charge
    RESERVED --> UNKNOWN: Provider outcome unclear
    UNKNOWN --> SETTLED: Reconciliation confirms usage
    UNKNOWN --> RELEASED: Reconciliation confirms no charge
    SETTLED --> [*]
    RELEASED --> [*]
```

A timeout does not prove the provider failed to process the request.
Keep ambiguous outcomes in an `UNKNOWN` or reconciliation-required state
instead of blindly releasing the reservation.

## 4. Phase 1 --- Budget Configuration System

### Step 1.1: Design entities

Initial entities: - Team - Agent - Session - BudgetPolicy -
BudgetAccount or BudgetWindow - ModelPricing - User/API credential, if
required for authentication

Keep policy configuration separate from period-specific usage.

Conceptual ER diagram:

``` mermaid
erDiagram
    TEAM ||--o{ AGENT : owns
    AGENT ||--o{ SESSION : creates
    TEAM ||--o{ BUDGET_POLICY : has
    AGENT ||--o{ BUDGET_POLICY : has
    SESSION ||--o{ BUDGET_POLICY : has
    BUDGET_POLICY ||--o{ BUDGET_ACCOUNT : creates_windows
    BUDGET_ACCOUNT ||--o{ RESERVATION : contains
    RESERVATION ||--o| USAGE_RECORD : settles_into
    MODEL_PRICING ||--o{ USAGE_RECORD : prices
```

This is conceptual, not a final schema. Decide whether a generic budget
policy table or separate typed account tables best fit the constraints.

### Step 1.2: Monetary representation

Use PostgreSQL `NUMERIC` and Python `Decimal` for monetary values. Do
not use binary floating-point for budget comparisons.

### Step 1.3: Models and migrations

-   Define SQLAlchemy 2.x declarative models.
-   Add primary/foreign keys, unique constraints, checks, and indexes.
-   Create Alembic migrations.
-   Test migration upgrade and downgrade on a disposable database.
-   Add deterministic development seed data.

### Step 1.4: API endpoints

``` text
POST   /api/v1/teams
GET    /api/v1/teams/{team_id}
POST   /api/v1/teams/{team_id}/agents
GET    /api/v1/agents/{agent_id}
POST   /api/v1/agents/{agent_id}/sessions
GET    /api/v1/sessions/{session_id}

POST   /api/v1/budget-policies
GET    /api/v1/budget-policies/{policy_id}
PATCH  /api/v1/budget-policies/{policy_id}

GET    /api/v1/teams/{team_id}/budget
GET    /api/v1/agents/{agent_id}/budget
GET    /api/v1/sessions/{session_id}/budget
```

Add authorization checks. Knowing a resource ID must not grant access to
that resource.

### Step 1.5: Tests

Test valid/invalid amounts, missing references, duplicate policies,
invalid windows, negative limits, unauthorized changes, and period
boundaries.

**Phase 1 exit:** Schema, migrations, CRUD APIs, validation, and tests
are complete.

## 5. Phase 2 --- LLM Gateway and Interception

### Step 2.1: Define request contract

Example logical request:

``` json
{
  "agent_id": "agent_123",
  "session_id": "session_456",
  "request_id": "unique-idempotency-key",
  "model": "preferred-model",
  "messages": [],
  "max_output_tokens": 1000
}
```

In deployment, derive identity from authenticated credentials or a
signed context. Do not trust arbitrary team or agent IDs supplied by an
unauthenticated client.

### Step 2.2: Provider interface

``` python
class LLMProvider:
    async def generate(self, request):
        raise NotImplementedError

    def estimate_input_tokens(self, request):
        raise NotImplementedError

    def get_usage(self, response):
        raise NotImplementedError
```

Refine this for streaming, cancellation, provider errors, and capability
metadata.

### Step 2.3: Mock provider

It should: - Return deterministic responses. - Return configurable token
usage. - Simulate latency. - Simulate timeouts and failures. - Simulate
missing usage metadata. - Support repeatable test scenarios.

### Step 2.4: Gateway

Initially authenticate, validate, call the mock provider, and return a
normalized response. Integrate reservation in Phase 4.

**Phase 2 exit:** Test agents reach the mock provider only through the
gateway.

## 6. Phase 3 --- Token Metering and Cost Calculation

### Step 3.1: Separate estimate from actual usage

Before request: - Estimate input tokens. - Reserve maximum permitted
output tokens. - Calculate conservative estimated cost.

After response: - Read provider-reported usage. - Calculate actual cost
using the request's pricing snapshot. - Store estimated and actual
values separately.

### Step 3.2: Cost formula

``` text
cost =
  (input_tokens * input_price_per_million
   + output_tokens * output_price_per_million)
  / 1_000_000
```

Use `Decimal`; define rounding at the ledger boundary. Providers may
charge for additional categories such as cached input, reasoning tokens,
images, or audio. Model those explicitly when supported.

### Step 3.3: Pricing model

Store provider, model identifier, input/output rates, currency,
effective period, pricing version, and optional modality-specific rates.

### Step 3.4: Tests

Test zero tokens, input-only/output-only usage, large counts, decimal
precision, price changes, missing metadata, and provider-specific token
categories.

**Phase 3 exit:** Estimates and settlements are deterministic and
traceable to a pricing version.

## 7. Phase 4 --- Atomic Budget Enforcement

This is the most correctness-sensitive phase.

### Step 4.1: Accounting values

``` text
settled_spend = sum of finalized usage
active_reserved = sum of active reservations
committed = settled_spend + active_reserved
available = limit - committed
```

Reserve estimated maximum cost `C` only when every applicable account
has `available >= C`.

### Step 4.2: Transaction and row locking

Lock every applicable budget account in a deterministic order, check all
limits, and create reservations in one transaction.

Illustrative SQL:

``` sql
BEGIN;

SELECT id, budget_limit, settled_spend, reserved_amount
FROM budget_accounts
WHERE id IN (:team_account, :agent_account, :session_account)
ORDER BY id
FOR UPDATE;

-- Application verifies that every account has enough capacity.

INSERT INTO reservations (...);

UPDATE budget_accounts
SET reserved_amount = reserved_amount + :estimated_cost
WHERE id IN (:team_account, :agent_account, :session_account);

COMMIT;
```

The real implementation must handle missing rows, period changes,
monetary types, and transaction isolation. Reservation records must
clearly identify every account they consume.

### Step 4.3: Settlement

After provider completion: 1. Start a new transaction. 2. Lock
reservation and relevant budget accounts consistently. 3. Verify
reservation state and idempotency key. 4. Record actual usage and cost.
5. Decrease active reserved amounts. 6. Increase settled spend. 7. Mark
reservation settled. 8. Commit.

If actual cost exceeds the reservation, record the overrun and apply the
documented policy. Never silently rewrite historical usage.

### Step 4.4: Failure handling

-   Failure before provider call: release reservation.
-   Confirmed provider rejection without processing: release
    reservation.
-   Provider succeeds: settle actual usage.
-   Timeout with unknown outcome: retain pending/unknown state and
    reconcile.
-   Crash after provider success but before settlement: reconcile using
    durable request and reservation IDs.
-   Duplicate callback/retry: idempotency prevents double settlement.

### Step 4.5: Warning and blocking

``` text
utilization = committed / budget_limit
```

At 80%, emit one warning per configured warning state/window. At 100%,
reject requests that cannot fit. A smaller request may still be accepted
if it fits every applicable remaining budget.

### Step 4.6: Session closure

When the session cannot accept another request: - Mark it
`budget_exhausted` or closed. - Reject new requests. - Allow in-flight
requests to settle. - Preserve its audit history.

### Step 4.7: Concurrency tests

Use multiple independent database sessions and concurrent workers. Test
shared team budgets, agent budgets, session budgets, rollback, lock
timeout, and deadlock behavior.

**Phase 4 exit:** No concurrent overspend in defined workloads;
reservations are auditable and recoverable.

## 8. Phase 5 --- Model Substitution

### Step 5.1: Model metadata

Represent provider/model ID, input/output prices, context limit,
modalities, tool-calling support, structured-output support,
availability, and policy allowlists.

### Step 5.2: Candidate selection

1.  Identify preferred model.
2.  Determine why its allocation is unavailable.
3.  Find permitted alternatives.
4.  Filter by required capabilities.
5.  Estimate each candidate's request cost.
6.  Rank according to policy and cost.
7.  Attempt reservation for each candidate.
8.  Select the first candidate whose reservation succeeds.
9.  Record the substitution reason.

Fallback cannot bypass team, agent, or session limits.

### Step 5.3: Tests

Test preferred available, preferred allocation exhausted, compatible
fallback, incompatible cheaper model, insufficient session budget, and
provider unavailability.

**Phase 5 exit:** Substitution is policy-driven, capability-aware, and
budget-safe.

## 9. Phase 6 --- Dashboard and Runaway Detection

### Step 6.1: Monitoring APIs

Provide team/agent/session utilization, spend over time, usage by
model/provider, rejected requests, and warning/runaway events.

### Step 6.2: Dashboard

Build budget cards, utilization bars, usage charts, substitution
history, rejected request table, runaway alerts, and authorized
pause/resume controls.

### Step 6.3: Rolling-window detector

``` text
spend_in_previous_60_minutes
    > 0.20 * monthly_agent_budget
```

Use a true rolling window. A timestamped usage query is acceptable
initially; optimize only after measuring.

On trigger: - Atomically mark agent paused or review-required. - Reject
new requests. - Create an evidence-backed alert. - Require authorized
human review to resume. - Define treatment of active reservations and
in-flight calls.

**Phase 6 exit:** Dashboard reconciles with ledger and runaway test
pauses the correct agent.

## 10. Phase 7 --- Evaluation and hardening

  -----------------------------------------------------------------------
  Scenario                            Expected result
  ----------------------------------- -----------------------------------
  Three concurrent agents             Correct usage per agent and team

  Budget reaches 80%                  One warning per warning
                                      state/window

  Request would cross 100%            Rejected before provider call

  Session budget exhausted            Session closed to new requests

  Preferred model allocation          Cheaper compatible model selected
  exhausted                           

  No valid fallback                   Request rejected

  Agent exceeds 20% monthly budget in Agent paused for review
  rolling hour                        

  Provider timeout                    Reservation reconciled safely

  Duplicate settlement                No double charge

  Database unavailable                Protected request fails closed

  Application restart                 Pending reservations recoverable

  Pricing changes                     Historical usage retains original
                                      pricing snapshot
  -----------------------------------------------------------------------

Measure gateway overhead, reservation/settlement latency, throughput,
lock waits, rejection latency, dashboard delay, and recovery time.
Report actual measurements, not invented performance claims.

## 11. Development workflow

``` text
1. Read the relevant concept.
2. Write expected behavior.
3. Draw the data flow or state transition.
4. Implement the smallest useful component.
5. Write unit tests.
6. Write integration tests.
7. Run the relevant test suite.
8. Inspect logs and database state.
9. Update progress.md.
10. Commit with a meaningful message.
```

Suggested commits:

``` text
docs: define AgentGuard architecture
feat(config): add team and agent budget policies
feat(gateway): add authenticated request interception
feat(metering): calculate and persist model usage
feat(budget): add atomic reservation workflow
test(budget): cover concurrent reservation races
```

## 12. End-of-phase review template

``` markdown
## Phase N Review

- **Problem solved:**
- **Architecture implemented:**
- **Techniques learned:**
- **Important design decisions:**
- **Files/modules created:**
- **Tests executed:**
- **Test results:**
- **Known limitations:**
- **What I can explain without notes:**
- **Next phase entry criteria:**
```

A phase is not fully understood until you can explain its design and
trade-offs without simply reading the code.
