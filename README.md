# AgentGuard

**Hierarchical Budget Enforcement and Runtime Governance for Multi-Agent LLM Systems**

AgentGuard is an infrastructure-level control plane that sits between AI agents and LLM providers. It intercepts requests, resolves trusted identity, applies budget policy, and is designed to reserve/settle spend before and after provider execution so overspending can be prevented at runtime rather than discovered after billing.

> **Current project phase:** **Phase 3 — Token Metering and Cost Calculation** (in progress)  
> **Last updated:** 2026-11-12  
> See [`progress.md`](progress.md) for detailed status, session log, and exit criteria.

## Project status

| Phase | Status | Focus | Exit evidence (high level) |
| --- | --- | --- | --- |
| 0. Foundations & Architecture | ✅ Complete | Requirements, invariants, architecture, repo plan | Documented in `project.md`, `implementation.md`, initial structure |
| 1. Budget Configuration System | ✅ Complete | Schema, migrations, policy/config APIs, validation | Models/migrations + CRUD/validation endpoints in backend (automated Phase 1 tests still pending) |
| 2. LLM Gateway & Interception | ✅ Complete | Authenticated gateway, mock provider path, idempotency/timeout handling | `POST /api/v1/gateway/chat/completions` + Phase 2 integration tests passing |
| 3. Token Metering & Cost Calculation | 🚧 In progress | Pricing/versioning, token estimation, provider usage, Decimal cost, usage persistence | Not started/completed yet (see checklist in `progress.md`) |
| 4. Atomic Budget Enforcement | ⏳ Planned | Reservations, settlement, concurrency-safe multi-level enforcement | — |
| 5. Intelligent Model Substitution | ⏳ Planned | Capability-aware, budget-safe fallback routing | — |
| 6. Monitoring & Runaway Detection | ⏳ Planned | Spend APIs, dashboard, rolling-window runaway detection | — |
| 7. Testing & Hardening | ⏳ Planned | Concurrency/failure/load testing, benchmarks, docs hardening | — |

## What is implemented today

- **Budget/configuration domain (Phase 1):** teams, agents, sessions, budget policies, pricing/model-related entities and Alembic migrations.
- **Gateway interception path (Phase 2):** authenticated gateway endpoint that resolves team/agent/session server-side, validates identities/status, enforces request correlation/idempotency, invokes a deterministic mock provider, and handles timeout/provider-error behavior.
- **Provider abstraction:** base provider interface and mock provider for deterministic, no-cost testing.
- **Domain scaffolding for later phases:** reservation/cost-related domain modules exist, but full metering, reservation lifecycle, settlement, and enforcement are not yet wired into the end-to-end request flow.
- **Frontend scaffold:** React + Vite + TypeScript app shell (dashboard/monitoring features planned for Phase 6).
- **Tests:** Phase 2 gateway integration tests (`backend/tests/test_gateway_phase2.py`).

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
│   ├── tests/               # backend tests (currently Phase 2 gateway tests)
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
- **Frontend:** React, TypeScript, Vite (scaffold; UI planned in later phases)

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

Run database migrations (from `backend/` or with appropriate config/path):

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

Start the API server:

```bash
uvicorn app.main:app --reload
```

> If running from the repository root, adjust `PYTHONPATH`/working directory as needed so `app.*` imports resolve correctly.

### 3. Frontend (scaffold)

```bash
cd frontend
npm install
npm run dev
```

The frontend is currently a scaffold; monitoring/dashboard functionality is planned for Phase 6.

## API highlights (current)

- **Configuration/policy APIs (Phase 1):** CRUD/management endpoints for teams, agents, sessions, and budget policies (see `backend/app/api/v1/router.py` and schemas).
- **Gateway endpoint (Phase 2):**
  - `POST /api/v1/gateway/chat/completions`
  - Requires trusted API-key authentication (`X-API-Key` / `GATEWAY_API_KEY`)
  - Resolves and validates identity server-side
  - Uses request correlation/idempotency handling
  - Routes through provider adapter (mock provider path implemented)

> Budget reservation/settlement is not yet enforced in the gateway request lifecycle; that is planned for Phases 3–4.

## Testing

Run the existing Phase 2 gateway tests:

```bash
PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/test_gateway_phase2.py -q
```

(Use your active Python environment/venv as appropriate.)

**Known testing gaps:** Phase 1 automated unit/API tests and later-phase concurrency/failure/load coverage are tracked in [`progress.md`](progress.md).

## Roadmap / next steps

Immediate focus (**Phase 3 — Token Metering and Cost Calculation**):
- Pricing schema and versioning
- Input-token estimation and max-output reservation inputs
- Provider-reported usage parsing
- Decimal-based cost calculation and rounding policy
- Usage persistence and precision tests

Planned follow-ups: atomic multi-level enforcement (Phase 4), capability-aware model substitution (Phase 5), monitoring/runaway detection dashboard (Phase 6), and hardening/benchmarking (Phase 7).

## Documentation

- [`project.md`](project.md) — problem statement, requirements, architecture, invariants, and phase definitions
- [`implementation.md`](implementation.md) — implementation guide and technical checklists
- [`progress.md`](progress.md) — live progress tracker, decisions, open questions, and work session log
- [`.env.example`](.env.example) — local environment variable template

## Notes

- Monetary values should use `NUMERIC`/`Decimal` semantics (no binary floating point for budget comparisons).
- This project is under active development; APIs, schemas, and enforcement behavior will evolve as phases are completed.
