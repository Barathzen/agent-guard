# AgentGuard --- Progress Tracker

**Current status:** In progress\
**Current phase:** Phase 6 --- Monitoring and Runaway Detection\
**Last updated:** 2026-11-13

> Mark a task complete only after implementation and verification.
> Reading about a technique or creating an initial draft is not
> implementation completion.

## Overall progress

-   [x] Phase 0 --- Foundations and Architecture
-   [x] Phase 1 --- Budget Configuration System
-   [x] Phase 2 --- LLM Gateway and Interception
-   [x] Phase 3 --- Token Metering and Cost Calculation
-   [ ] Phase 4 --- Atomic Budget Enforcement (implementation complete; hardening tests pending)
-   [ ] Phase 5 --- Intelligent Model Substitution (core routing complete; model allocations pending)
-   [ ] Phase 6 --- Monitoring and Runaway Agent Detection (core implementation complete; boundary tests pending)
-   [ ] Phase 7 --- Testing and Hardening

## Phase status

  ------------------------------------------------------------------------
  Phase             Status            Deliverable        Exit evidence
  ----------------- ----------------- ------------------ -----------------
  0\. Foundations   Complete          Architecture,      Documented in
                                      invariants,        `project.md`,
                                      repository plan    `implementation.md`,
                                                         and initial repo
                                                         structure

  1\. Configuration Complete          Budget policy APIs Schema/migrations,
                                      and schema         CRUD/validation
                                                         endpoints in
                                                         backend; no
                                                         automated test
                                                         suite recorded

  2\. Gateway       Complete          Intercepting       Authenticated
                                      FastAPI gateway    gateway endpoint,
                                                         mock provider path,
                                                         idempotency/
                                                         timeout behavior,
                                                         and Phase 2 tests
                                                         passing

  3\. Metering      Complete          Token and cost     Calculation tests,
                                      ledger              versioned pricing,
                                                         usage persistence

  4\. Enforcement   Not started       Reservation and    Concurrency and
                                      settlement engine  failure tests

  5\. Routing       Not started       Capability-aware   Substitution
                                      fallback router    tests

  6\. Monitoring    Not started       Dashboard and      Live updates and
                                      runaway detector   threshold tests

  7\. Hardening     Not started       Benchmarks and     Acceptance suite
                                      final              and benchmark
                                      documentation      report
  ------------------------------------------------------------------------

## Phase 0 --- Foundations and Architecture

-   [x] Confirm project problem statement and scope.
-   [x] Separate functional and non-functional requirements.
-   [x] Define team, agent, session, and model identities.
-   [x] Define budget windows, currency, timezone, and reset semantics.
-   [x] Define whether active reservations count toward committed spend.
-   [x] Define request lifecycle and trust boundaries.
-   [x] Finalize high-level architecture diagram.
-   [x] Finalize request sequence diagram.
-   [x] Define repository structure and local environment.
-   [x] Record PostgreSQL-first decision and why Redis is excluded.

**Exit:** Architecture and core invariants are documented and internally
consistent (`project.md`, `implementation.md`, decision log). Some
operational details remain open decisions for later phases.

## Phase 1 --- Budget Configuration

-   [x] Design ER diagram.
-   [x] Define teams, agents, sessions, budget policies, and model
    pricing.
-   [x] Define budget periods and currency precision.
-   [x] Define SQLAlchemy models and constraints.
-   [x] Create Alembic migration.
-   [x] Implement policy CRUD endpoints.
-   [x] Add authorization and validation.
-   [ ] Add unit and API tests.

**Exit:** Phase 1 marked complete per current project state. Core schema,
migrations, CRUD/configuration endpoints, and request validation exist in
the backend (`backend/app/db/models.py`,
`backend/app/api/v1/router.py`, `backend/app/api/v1/schemas.py`,
`backend/migrations/versions/0002_phase1_entities.py`). Automated
unit/API test coverage for Phase 1 is not present in the repository and
remains a follow-up hardening item.

## Phase 2 --- Gateway

-   [x] Define gateway request/response schemas.
-   [x] Define trusted agent authentication.
-   [x] Resolve team, agent, and session server-side.
-   [x] Define provider adapter interface.
-   [x] Implement deterministic mock provider.
-   [x] Implement gateway endpoint.
-   [x] Add request correlation and idempotency identifiers.
-   [x] Add timeout and cancellation behavior.
-   [x] Add integration tests.

**Exit:** Test agents reach the mock provider only through the gateway.
Verified by `backend/tests/test_gateway_phase2.py` covering authenticated
access, server-side identity/status validation, gateway-to-mock-provider
completion responses, request correlation/idempotency handling, timeout
and provider-error behavior. Phase 2 does not yet perform budget
reservation/settlement (deferred to Phase 3/4).

## Phase 3 --- Metering

-   [x] Define pricing schema and versioning.
-   [x] Implement input-token estimation.
-   [x] Calculate the maximum-output estimate (reservation remains Phase 4).
-   [x] Parse provider-reported usage.
-   [x] Implement cost calculation using Decimal.
-   [x] Reject requests when pricing metadata is missing.
-   [x] Persist usage records.
-   [x] Test precision and rounding.

**Exit:** Estimates and usage records are deterministic and traceable to
versioned pricing. Budget reservation and settlement remain in Phase 4.

## Phase 4 --- Atomic Enforcement

-   [x] Define reservation state machine.
-   [x] Define budget account and reservation semantics.
-   [x] Implement deterministic row-lock ordering.
-   [x] Implement atomic multi-level reservation.
-   [x] Implement reservation expiry and recovery.
-   [x] Implement idempotent settlement.
-   [x] Implement unused-reservation release.
-   [x] Implement 80% warning behavior.
-   [x] Implement 100% hard block.
-   [x] Implement session closure.
-   [ ] Test concurrent requests and shared budgets.
-   [ ] Test provider timeout and process-crash scenarios.

**Exit:** Core reservation, warning, settlement, release, timeout,
recovery, and session-exhaustion paths are implemented and the live
PostgreSQL integration probe passes. Dedicated concurrent and crash
recovery tests remain in the Phase 7 hardening backlog.

## Phase 5 --- Model Substitution

-   [x] Define model capability metadata.
-   [x] Define preferred and allowed fallback models.
-   [ ] Define optional model-level allocation.
-   [x] Implement candidate filtering and cost comparison.
-   [x] Re-check every applicable budget for fallback.
-   [x] Record selected model and substitution reason.
-   [x] Test unavailable and incompatible fallbacks.

**Exit:** Only cheaper, compatible, permitted models that fit all
budgets are selected. Optional model-level allocation remains a
follow-up before the full phase exit.

## Phase 6 --- Monitoring and Runaway Detection

-   [x] Implement spend summary APIs.
-   [x] Implement team, agent, and session utilization APIs.
-   [x] Implement usage history APIs.
-   [x] Build dashboard pages.
-   [x] Implement WebSocket or SSE updates.
-   [x] Implement rolling 60-minute spend calculation.
-   [x] Implement 20% monthly-budget runaway threshold.
-   [x] Implement agent pause and resume.
-   [x] Implement human review and audit events.
-   [ ] Test time-window boundaries.

**Exit:** Dashboard reads the ledger through monitoring APIs and SSE,
and the live PostgreSQL probe pauses the correct runaway agent and
creates an audit event. Time-boundary tests remain in the hardening
backlog.

## Phase 7 --- Testing and Hardening

-   [ ] Test three concurrent agents.
-   [ ] Test multiple agents sharing one team budget.
-   [ ] Test 80% warning boundary.
-   [ ] Test 100% rejection boundary.
-   [ ] Test session closure.
-   [ ] Test model substitution.
-   [ ] Test duplicate requests and settlements.
-   [ ] Test provider timeout and cancellation.
-   [ ] Test database outage behavior.
-   [ ] Test application restart with pending reservations.
-   [ ] Run load and concurrency benchmarks.
-   [ ] Record latency and throughput.
-   [ ] Review security boundaries.
-   [ ] Complete setup and operations documentation.

**Exit:** Acceptance suite passes and limitations are documented.

## Decision log

  -----------------------------------------------------------------------
  Date              Decision          Reason            Revisit condition
  ----------------- ----------------- ----------------- -----------------
  2026-11-08        PostgreSQL is the ACID transactions Measured
                    only initial      and row-level     bottleneck
                    datastore         locking support   justifies another
                                      the first correct store
                                      implementation    

  2026-11-08        Do not add Redis  Avoid extra       Benchmark
                    initially         consistency       supports Valkey
                                      complexity before or another
                                      it is needed      counter store

  2026-11-08        Use a mock LLM    Deterministic,    Real provider
                    provider first    free, repeatable  adapter phase
                                      tests             

  2026-11-08        Keep provider     Prevent supported Deployment
                    credentials       agents from       architecture
                    behind gateway    bypassing         review
                                      enforcement       

  2026-11-12        Use local         Development       Containerized
                    PostgreSQL        machine has no    setup needed for
                    instead of Docker Docker; native   deployment
                                      Postgres
                                      available

  2026-11-12        Create schema via Ensures           Migration
                    Alembic           `alembic_version` workflow changes
                    (`init_db.py`)    stays consistent
                    instead of        for future
                    `create_all`      migrations
  -----------------------------------------------------------------------

## Work session log

### Session 0 --- Initial documentation

-   **Date:** 2026-11-08
-   **Phase:** Planning / Phase 0
-   **Completed:** Initial scope, architecture outline, phase plan, and
    implementation checklist.
-   **Files:** `project.md`, `progress.md`, `implementation.md`
-   **Tests:** Not applicable.
-   **Blockers:** None recorded.
-   **Next:** Confirm architecture assumptions and create repository
    skeleton.

### Session 1 --- Phase 1 close-out and progress alignment

-   **Date:** 2026-11-11
-   **Phase:** Phase 1 complete / Phase 2 in progress
-   **Completed:** Reviewed `project.md`, `implementation.md`, and current
    repository state; marked Phase 0 and Phase 1 as complete in the
    tracker; recorded Phase 1 exit evidence and noted missing automated
    tests as follow-up work.
-   **Files changed:** `progress.md`
-   **Tests run:** Not run (documentation/state alignment only).
-   **Results:** Progress tracker now reflects Phase 1 ended and sets
    current phase to Phase 2.
-   **Decisions:** Treat existing budget configuration schema, migrations,
    CRUD endpoints, and validation as Phase 1 completion evidence while
    explicitly tracking absent automated test coverage.
-   **Blockers:** No dedicated Phase 1 unit/API tests found in repository.
-   **Next:** Complete Phase 2 gateway interception flow (authenticated
    identity resolution, request handling, provider integration path,
    idempotency/timeout behavior) and add integration tests.

### Session 2 --- Phase 2 gateway completion

-   **Date:** 2026-11-12
-   **Phase:** Phase 2 complete / Phase 3 next
-   **Completed:** Implemented authenticated LLM gateway interception path
    (`POST /api/v1/gateway/chat/completions`) with trusted API-key auth,
    server-side team/agent/session resolution and status validation,
    request correlation/idempotency enforcement, timeout/cancellation-aware
    provider invocation, and mock-provider responses. Added/updated gateway
    schemas, provider abstractions, mock provider, configuration, and
    `Reservation`/`ReservationState` model alignment used by existing
    domain scaffolding; added Phase 2 integration tests.
-   **Files changed:** `backend/app/api/v1/router.py`,
    `backend/app/api/v1/schemas.py`, `backend/app/core/config.py`,
    `backend/app/db/models.py`, `backend/tests/conftest.py`,
    `backend/tests/test_gateway_phase2.py`, `progress.md`
-   **Tests run:** `cd agent-guard && PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/test_gateway_phase2.py -q`
-   **Results:** `5 passed, 5 warnings in 0.97s` (Pydantic v2 deprecation
    warnings from existing schema config style; pytest-asyncio loop-scope
    warning).
-   **Decisions:** Enforced trusted gateway access via `X-API-Key`
    (`GATEWAY_API_KEY`) and treated duplicate `request_id` values as
    idempotency conflicts (409). Gateway validates client-supplied IDs
    against server-resolved DB relationships/status instead of trusting
    them implicitly.
-   **Blockers:** Budget reservation/settlement is not yet wired into the
    gateway request lifecycle (planned for Phases 3/4). Existing Pydantic
    class-based config deprecation warnings remain.
-   **Next:** Begin Phase 3 metering/cost calculation (pricing schema and
    versioning, input-token estimation/max-output reservation inputs,
    provider-reported usage handling, `Decimal` cost calculation, usage
    persistence, precision tests). Also add Phase 1 API/unit tests as
    hardening follow-up.

### Session 3 --- Local PostgreSQL and database init script

-   **Date:** 2026-11-12
-   **Phase:** Phase 3 in progress (environment/tooling work)
-   **Completed:** Switched local database setup from Docker Compose to a
    natively installed PostgreSQL instance. Removed `docker-compose.yml`,
    updated `.env.example` and `backend/app/core/config.py` for
    `localhost:5432`, and made settings load `.env` from either `backend/`
    or the repository root. Added `backend/scripts/init_db.py`, which
    applies all Alembic migrations to create the full schema (with
    `--sql` preview support and masked credentials in output). Updated
    `README.md` setup instructions.
-   **Files changed:** `.env.example`, `backend/app/core/config.py`,
    `backend/scripts/init_db.py`, `README.md`, `implementation.md`,
    `progress.md`; removed `docker-compose.yml`.
-   **Tests run:** `python -m py_compile backend/scripts/init_db.py`;
    `python backend/scripts/init_db.py --sql` (offline SQL generation);
    `python backend/scripts/init_db.py` (live); `psql -d agentguard -c "\dt"`
-   **Results:** Syntax check passed. Offline SQL generation produced the
    full schema. Recreated `.venv` with Python 3.12 (pinned dependencies
    have no Python 3.14 wheels) and installed
    `backend/requirements.txt` successfully. Created the local
    `agentguard` database, then applied migrations `0001` and `0002`.
    Verified 8 tables exist (`teams`, `agents`, `sessions`,
    `budget_policies`, `budget_accounts`, `reservations`,
    `model_pricings`, `alembic_version`) with `alembic_version` at
    `0002`.
-   **Decisions:** Use a local PostgreSQL installation instead of Docker.
    Schema creation is performed through Alembic migrations (via
    `init_db.py`) rather than raw `create_all`, so `alembic_version`
    stays consistent and future migrations apply cleanly. Standardize
    local development on Python 3.12.
-   **Blockers:** None. Local database is initialized and ready.
-   **Next:** Continue Phase 3 metering/cost calculation work using the
    local PostgreSQL database.

### Session 4 --- Phase 4 atomic enforcement

- **Date:** 2026-11-13
- **Phase:** Phase 4 in progress (core implementation complete)
- **Completed:** Added the Phase 4 warning-event schema/migration; implemented
  deterministic row-lock reservation, idempotent settlement, provider-error
  release, timeout/cancellation unknown-state handling, stale reservation
  recovery, warning deduplication, session exhaustion, and gateway wiring.
- **Files changed:** `backend/app/db/models.py`,
  `backend/app/domain/reservation.py`, `backend/app/api/v1/router.py`,
  `backend/app/api/v1/schemas.py`, `backend/app/core/config.py`,
  `backend/migrations/versions/0004_phase4_enforcement.py`,
  `.env.example`, `progress.md`
- **Tests run:** Phase 2/3 suite (`9 passed`); migration SQL generation;
  live migration; live PostgreSQL reservation/warning/settlement/idempotency
  probe; live gateway reserve/settle integration probe.
- **Results:** All listed checks passed. Concurrent and crash-recovery
  acceptance tests remain for hardening.
- **Decisions:** Unknown reservations retain their holds until reconciliation;
  warning events are unique per account and budget window.
- **Blockers:** None for the core implementation.
- **Next:** Add concurrent shared-budget and crash-recovery tests.

### Session 5 --- Phase 5 model substitution

- **Date:** 2026-11-13
- **Phase:** Phase 5 in progress (core routing complete)
- **Completed:** Added persisted model capability metadata and per-agent
  route policies; implemented capability/context/availability filtering,
  cheaper fallback selection, per-candidate pricing and budget reservation
  retries, selected-model response metadata, substitution reasons, and
  configuration endpoints.
- **Files changed:** `backend/app/db/models.py`,
  `backend/app/domain/routing.py`, `backend/app/api/v1/router.py`,
  `backend/app/api/v1/schemas.py`,
  `backend/migrations/versions/0005_phase5_model_routing.py`,
  `backend/tests/test_routing_phase5.py`, `progress.md`
- **Tests run:** Phase 5 routing plus Phase 2/3 regression suite
  (`12 passed`); Python compilation; migration SQL generation; live
  migration application; diff check.
- **Results:** All checks passed. Candidate filtering and fallback
  behavior are covered; optional model-level budget allocation is not yet
  implemented.
- **Decisions:** Fallbacks require persisted capability metadata and must
  be no more expensive than the requested model. Each candidate is
  re-reserved against all applicable budgets before provider invocation.
- **Blockers:** None.
- **Next:** Add model-level allocation accounting, then proceed to Phase 6.

### Session 6 --- Phase 6 monitoring and runaway detection

- **Date:** 2026-11-13
- **Phase:** Phase 6 in progress (core implementation complete)
- **Completed:** Added spend summaries for team/agent/session accounts,
  usage and audit history APIs, rolling-window spend calculations,
  configurable runaway detection at 20% of the monthly agent budget,
  durable audit events, manual agent pause/resume, runaway scan endpoint,
  SSE budget updates, and a live dashboard.
- **Files changed:** `backend/app/db/models.py`,
  `backend/app/domain/monitoring.py`, `backend/app/api/v1/router.py`,
  `backend/app/api/v1/schemas.py`,
  `backend/migrations/versions/0006_phase6_monitoring.py`,
  `backend/app/core/config.py`, `.env.example`,
  `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`,
  `progress.md`
- **Tests run:** Backend regression suite (`12 passed`), frontend
  production build, Python compilation, migration SQL generation and
  application, ORM audit table query, and live PostgreSQL monitoring
  summary/runaway/audit probe.
- **Results:** All checks passed. Existing Pydantic/pytest deprecation
  warnings remain; time-window boundary tests are not yet added.
- **Decisions:** Runaway detection uses actual settled spend in the
  configurable rolling 60-minute window and pauses active agents when it
  reaches the configured monthly-budget fraction. All status changes emit
  durable audit events.
- **Blockers:** None.
- **Next:** Add time-window boundary tests and continue Phase 7 hardening.

### Append this template after each session

``` markdown
### Session N — Short title

- **Date:**
- **Phase:**
- **Completed:**
- **Files changed:**
- **Tests run:**
- **Results:**
- **Decisions:**
- **Blockers:**
- **Next:**
```

## Open decisions

-   [ ] Calendar month or rolling 30-day budget period?
-   [ ] Currency and currency conversion policy?
-   [ ] How do budget decreases interact with active reservations?
-   [ ] Reservation expiry and crash-recovery policy?
-   [ ] Streaming response settlement and client cancellation?
-   [ ] Provider-specific usage metadata handling?
-   [ ] Capability requirements for fallback models?
-   [ ] Do in-flight requests finish after session exhaustion?
-   [ ] Who can pause/resume agents and edit budgets?
-   [ ] Fail-closed behavior during database outage?

## Update rules

1.  Update status only after evidence exists.
2.  Record exact test commands and outcomes.
3.  Add important choices to the decision log.
4.  Record blockers instead of silently skipping them.
5.  Update current phase and last-updated date.
6.  Do not mark a feature complete just because its endpoint exists.
