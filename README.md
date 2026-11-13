# AgentGuard

**Hierarchical Budget Enforcement and Runtime Governance for Multi-Agent LLM Systems**

AgentGuard is an infrastructure-level control plane that sits between AI agents and LLM providers. It intercepts requests, resolves trusted identity, applies budget policy, and is designed to reserve/settle spend before and after provider execution so overspending can be prevented at runtime rather than discovered after billing.

> **Current project phase:** **Phase 7 — Testing and Hardening** (acceptance complete)
> **Last updated:** 2026-11-13
> See [`progress.md`](progress.md) for detailed status, session log, and exit criteria.

## Project status

| Phase | Status | Focus | Exit evidence (high level) |
| --- | --- | --- | --- |
| 0. Foundations & Architecture | ✅ Complete | Requirements, invariants, architecture, repo plan | Documented in `project.md`, `implementation.md`, initial structure |
| 1. Budget Configuration System | ✅ Complete | Schema, migrations, policy/config APIs, validation | Models/migrations + CRUD/validation endpoints in backend (automated Phase 1 tests still pending) |
| 2. LLM Gateway & Interception | ✅ Complete | Authenticated gateway, mock provider path, idempotency/timeout handling | `POST /api/v1/gateway/chat/completions` + Phase 2 integration tests passing |
| 3. Token Metering & Cost Calculation | ✅ Complete | Pricing/versioning, token estimation, provider usage, Decimal cost, usage persistence | Metering tests and live PostgreSQL verification |
| 4. Atomic Budget Enforcement | ✅ Complete | Reservations, settlement, concurrency-safe multi-level enforcement | PostgreSQL hardening tests |
| 5. Intelligent Model Substitution | ✅ Complete | Capability-aware, budget-safe fallback routing | Routing tests and model allocations |
| 6. Monitoring & Runaway Detection | ✅ Complete | Spend APIs, dashboard, rolling-window runaway detection | Monitoring probes and dashboard build |
| 7. Testing & Hardening | 🚧 Acceptance complete | Concurrency/failure/load testing, security and operations hardening | 17 backend tests, migration `0007`, frontend build |

## What is implemented today

- **Budget/configuration domain (Phase 1):** teams, agents, sessions, budget policies, pricing/model-related entities and Alembic migrations.
- **Gateway interception path (Phase 2):** authenticated gateway endpoint that resolves team/agent/session server-side, validates identities/status, enforces request correlation/idempotency, invokes a deterministic mock provider, and handles timeout/provider-error behavior.
- **Provider abstraction:** base provider interface and mock provider for deterministic, no-cost testing.
- **Enforcement and routing:** PostgreSQL row-locked reservations, idempotent settlement/release, unknown-state recovery, capability-aware fallback, and optional per-agent/model allocations.
- **Monitoring:** live spend/usage/audit APIs, SSE budget updates, runaway-agent pause/resume, and the React dashboard.
- **Tests:** PostgreSQL hardening coverage in `backend/tests/test_phase7_hardening.py` plus gateway outage coverage.

## Architecture overview

Core request lifecycle (target design):

1. Agent sends request to AgentGuard gateway.
2. Gateway authenticates caller and resolves team/agent/session identity.
3. Gateway estimates request cost and checks applicable budgets.
4. A database transaction atomically reserves estimated spend.
5. Router selects preferred or permitted fallback model.
6. Provider adapter executes the request.
7. Actual usage is recorded and reservation is settled/released.
8. Usage/audit events feed monitoring and runaway detection.

**Initial storage decision:** PostgreSQL only (transactions, row-level locking, constraints/idempotency). Redis/Valkey is intentionally deferred until measurements justify it.

**Security boundary:** AgentGuard can only enforce requests routed through it. Provider credentials should remain behind the gateway; direct provider access bypasses enforcement.

For full architecture, invariants, and phase plans, see [`project.md`](project.md) and [`implementation.md`](implementation.md).

## Repository structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API routes and schemas (config + gateway)
│   │   ├── core/            # settings/config, database setup
│   │   ├── db/              # SQLAlchemy models
│   │   ├── domain/          # domain logic/scaffolding (calculator, reservation, etc.)
│   │   ├── providers/       # LLM provider adapters (base, mock)
│   │   └── main.py          # FastAPI app entrypoint
│   ├── migrations/          # Alembic migrations
│   ├── scripts/             # local setup utilities (init_db.py)
│   ├── tests/               # gateway, routing, and PostgreSQL hardening tests
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/                # React + Vite + TypeScript scaffold
├── .env.example             # local PostgreSQL/environment template
├── project.md               # project overview, requirements, architecture
├── implementation.md        # phase-by-phase implementation guide
└── progress.md              # current phase, checklist, decisions, session log
```

## Tech stack

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic
- **Database:** PostgreSQL (local installation)
- **Testing:** pytest, pytest-asyncio, httpx
- **Providers:** mock provider now; adapter-based design for future providers (e.g. Ollama/others)
- **Frontend:** React, TypeScript, Vite monitoring dashboard

## Getting started (local development)

### Prerequisites

- Python 3.11–3.13 (**3.12 recommended**; Python 3.14 is not yet supported by the pinned dependencies)
- Node.js/npm (for frontend)
- PostgreSQL 16+ installed and running locally

### 1. Prepare local PostgreSQL

Create the development database (adjust `DATABASE_URL`/credentials as needed):

```bash
createdb agentguard
```

If your local PostgreSQL uses different credentials, update `DATABASE_URL` in `.env` (see `.env.example`). Default template uses:
- Host: `localhost`
- Port: `5432`
- DB: `agentguard`

### 2. Backend setup

```bash
py -3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Copy `.env.example` to `.env` and update the credentials to match your local PostgreSQL instance:

```bash
cp .env.example .env
```

At minimum, ensure `DATABASE_URL` points to your local Postgres instance and set `GATEWAY_API_KEY` for authenticated gateway access.

Run database migrations:

```bash
cd backend
alembic upgrade head
```

Or create all tables in one step from the repository root using the setup script (it applies the same Alembic migrations):

```bash
python backend/scripts/init_db.py
```

Preview the SQL without executing it:

```bash
python backend/scripts/init_db.py --sql
```

Start the API server from the repository root:

```bash
PYTHONPATH=$PWD .venv/bin/uvicorn backend.app.main:app --reload
```

If your virtual environment is inside `backend/`, start it from the
`backend/` directory with the repository root added to `PYTHONPATH`:

```bash
cd backend
PYTHONPATH=.. .venv/bin/uvicorn app.main:app --reload
```

Running `uvicorn app.main:app --reload` without `PYTHONPATH=..` from
`backend/` fails because the application imports the top-level
`backend.app` package.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard calls authenticated monitoring endpoints. Set `VITE_GATEWAY_API_KEY` when the development API key is not `dev-gateway-key`.
For a different seeded identity, also set `VITE_TEAM_ID`, `VITE_AGENT_ID`,
and `VITE_SESSION_ID`. The defaults are `team_core`, `agent_coder`, and
`session_init_01`.

## API highlights (current)

- **Configuration/policy APIs (Phase 1):** CRUD/management endpoints for teams, agents, sessions, and budget policies (see `backend/app/api/v1/router.py` and schemas).
- **Gateway endpoint:**
  - `POST /api/v1/gateway/chat/completions`
  - Requires trusted API-key authentication (`X-API-Key` / `GATEWAY_API_KEY`)
  - Resolves and validates identity server-side
  - Uses request correlation/idempotency handling
  - Routes through provider adapter and enforces reservation/settlement
- **Model and monitoring APIs:**
  - `POST /api/v1/model-capabilities`
  - `POST /api/v1/agents/{agent_id}/model-route-policy`
  - `POST /api/v1/agents/{agent_id}/model-allocations`
  - `GET /api/v1/agents` (registered agent roster)
  - `GET /api/v1/monitoring/summary/{scope}/{entity_id}`
  - `GET /api/v1/monitoring/usage`, `GET /api/v1/monitoring/audit`
  - `POST /api/v1/monitoring/runaway/scan`, `POST /api/v1/agents/{agent_id}/pause|resume`
  - `GET /api/v1/monitoring/stream` (Server-Sent Events)

All `/api/v1` routes require `X-API-Key`. Configure
`CORS_ALLOWED_ORIGINS` explicitly; the default permits local development
origins on common development ports 3000, 5173, and 5174.

## Testing

Run the backend acceptance suite from the repository root:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest backend/tests -q
```

Run the reservation benchmark against an existing budget account. It
reserves and releases each sample, so it does not add settled spend:

```bash
PYTHONPATH=$PWD .venv/bin/python backend/scripts/benchmark_reservations.py ACCOUNT_ID 200 16
```

The benchmark reports throughput and p50/p95/max latency. The current
local reference run used 200 samples at concurrency 16:

- Throughput: 100.72 operations/second
- p50 latency: 105.22 ms
- p95 latency: 695.17 ms
- Maximum latency: 805.13 ms

The benchmark is environment-dependent and should be rerun after database,
pool, or deployment changes.

## Operations and security

- Apply schema changes with `alembic upgrade head`; verify the resulting
  revision with `alembic current`.
- PostgreSQL is authoritative for reservations, settled spend, usage, and
  audit records. Redis/Valkey is not required by the current design.
- Database failures fail closed: the gateway returns `503` before provider
  execution. Reservations in an unknown state retain their holds until
  reconciliation or stale-reservation recovery.
- Keep provider credentials on the server side. Direct provider access
  bypasses AgentGuard enforcement.
- Replace `dev-gateway-key` with a secret-managed API key outside local
  development. Never commit `.env` or credentials.
- Set `CORS_ALLOWED_ORIGINS` to the exact dashboard origins required by the
  deployment; do not use a wildcard in production.

## Current status

Phases 0–6 are complete. Phase 7 acceptance and operational hardening are
complete, including 17 PostgreSQL-backed backend tests, migration `0007`,
database-outage coverage, security-boundary hardening, and a production
frontend build. See [`progress.md`](progress.md) for executable evidence
and the remaining production-deployment considerations.

## Documentation

- [`project.md`](project.md) — problem statement, requirements, architecture, invariants, and phase definitions
- [`implementation.md`](implementation.md) — implementation guide and technical checklists
- [`progress.md`](progress.md) — live progress tracker, decisions, open questions, and work session log
- [`.env.example`](.env.example) — local environment variable template

## Notes

- Monetary values use `NUMERIC`/`Decimal` semantics; budget comparisons do
  not use binary floating point.
- Provider calls occur outside reservation transactions. Successful calls
  settle actual usage, confirmed provider errors release reservations, and
  timeouts or cancellation move reservations to `UNKNOWN`.
