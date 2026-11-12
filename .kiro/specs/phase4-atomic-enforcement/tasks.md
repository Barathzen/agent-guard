# Implementation Plan: Phase 4 — Atomic Budget Enforcement

## Overview

Wire atomic reservation and settlement into the AgentGuard gateway. All tasks target the existing Python/FastAPI/SQLAlchemy/pytest stack. The implementation language is Python. Each task builds directly on the previous one; no step leaves unintegrated code.

---

## Tasks

- [ ] 1. Add `BudgetWarningEvent` model and Alembic migration
  - [ ] 1.1 Define `BudgetWarningEvent` SQLAlchemy model in `backend/app/db/models.py`
    - Add `BudgetWarningEvent` class with columns: `id` (String 64, PK), `account_id` (String 64, not null), `threshold_pct` (Integer, not null), `utilization_pct` (Numeric 7,4, not null), `window_key` (String 32, not null), `created_at` (DateTime tz-aware, not null)
    - Add `UniqueConstraint("account_id", "window_key", name="uq_warning_account_window")` in `__table_args__`
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 1.2 Add `RESERVATION_STALENESS_MINUTES` and `RESERVATION_RECOVERY_INTERVAL_MINUTES` fields to `Settings` in `backend/app/core/config.py`
    - Default values: `60` and `5` respectively
    - _Requirements: 6.3, 6.4_
  - [ ] 1.3 Create Alembic migration `backend/migrations/versions/0004_phase4_enforcement.py`
    - Creates `budget_warning_events` table with all columns and the unique constraint
    - Provides a valid `downgrade()` that drops the table
    - _Requirements: 7.1_

- [ ] 2. Refactor `atomic_reserve` and `atomic_settle` in `backend/app/domain/reservation.py`
  - [ ] 2.1 Refactor `atomic_reserve` to not call `session.commit()` internally
    - Remove the `await session.commit()` call; the caller (gateway) will manage the transaction boundary
    - Keep all existing logic: sorted lock ordering, availability check, `reserved_amount` increment, `Reservation` insert
    - Return `False` (not raise) when any account is missing or any account has `available < estimated_cost`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [ ] 2.2 Add idempotency guard to `atomic_settle`
    - Lock the `Reservation` row first (before accounts), check `reservation.state`
    - If `state == SETTLED`: return without changes (idempotent no-op)
    - If `state` is `RELEASED` or `UNKNOWN`: raise `InvalidStateTransitionError` (define this exception in `reservation.py`)
    - If `state == RESERVED`: proceed with existing settlement logic
    - Remove the internal `await session.commit()`; caller manages transaction
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 2.3 Add `atomic_release` function to `backend/app/domain/reservation.py`
    - Accepts: `session, account_ids, estimated_cost, request_id`
    - Lock reservation (FOR UPDATE), verify `state == RESERVED`; raise `InvalidStateTransitionError` otherwise
    - Decrement `reserved_amount` by `estimated_cost` on all accounts (locked in sorted order)
    - Set `reservation.state = RELEASED`
    - Do NOT call `session.commit()` — caller manages transaction
    - _Requirements: 4.1, 4.2_
  - [ ] 2.4 Add `mark_unknown` function to `backend/app/domain/reservation.py`
    - Accepts: `session, request_id`
    - Lock reservation (FOR UPDATE), verify `state == RESERVED`; raise `InvalidStateTransitionError` otherwise
    - Set `reservation.state = UNKNOWN`; do NOT modify `reserved_amount` on any account
    - Do NOT call `session.commit()` — caller manages transaction
    - _Requirements: 5.1, 5.2_
  - [ ]* 2.5 Write unit tests for refactored domain functions in `backend/tests/test_enforcement_phase4.py`
    - Test `atomic_reserve` returns `True` when all accounts sufficient, returns `False` when any account insufficient, does not commit internally
    - Test `atomic_settle` idempotency: second call with SETTLED reservation is a no-op
    - Test `atomic_settle` raises `InvalidStateTransitionError` for RELEASED/UNKNOWN states
    - Test `atomic_release` decrements `reserved_amount` and leaves `settled_spend` unchanged
    - Test `mark_unknown` leaves `reserved_amount` unchanged, sets state to UNKNOWN
    - Use `pytest-asyncio` with an in-process SQLite or PostgreSQL test database
    - _Requirements: 1.3, 1.4, 3.3, 3.4, 4.1, 4.2, 5.1, 5.2_

- [ ] 3. Implement `BudgetWarningService` in `backend/app/domain/warning.py`
  - [ ] 3.1 Create `backend/app/domain/warning.py` with `BudgetWarningService` class
    - Implement `check_and_emit(db, accounts, policies)` method
    - For each account: compute `window_key` based on policy period (MONTHLY → `"YYYY-MM"` from UTC now, SESSION_LIFETIME → `session_id` passed via policy, ROLLING_30_DAYS → ISO week string)
    - Check `utilization_pct = committed / budget_limit * 100`; if `>= policy.warning_threshold_pct`, attempt insert of `BudgetWarningEvent`
    - Use `INSERT ... ON CONFLICT DO NOTHING` (or catch `IntegrityError`) to enforce uniqueness without raising
    - Return list of newly inserted event IDs
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [ ]* 3.2 Write unit tests for `BudgetWarningService` in `backend/tests/test_enforcement_phase4.py`
    - **Property 9: Warning idempotence per budget window**
    - Test: for any sequence of calls with utilization above threshold, exactly one `BudgetWarningEvent` row exists per `(account_id, window_key)`
    - Test: no warning emitted when utilization is below threshold
    - Test: `window_key` format for MONTHLY is `"YYYY-MM"` and for SESSION_LIFETIME is session ID
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 4. Implement `SessionExhaustionService` in `backend/app/domain/exhaustion.py`
  - [ ] 4.1 Create `backend/app/domain/exhaustion.py` with `SessionExhaustionService` class
    - Implement `check_and_close(db, session_id)` method
    - Load the `BudgetAccount` for the given `session_id`; if `available <= 0`, set `Session.status = SessionStatus.EXHAUSTED`
    - Return `True` if session was closed, `False` otherwise
    - _Requirements: 9.1_
  - [ ]* 4.2 Write unit tests for `SessionExhaustionService` in `backend/tests/test_enforcement_phase4.py`
    - Test: session transitions to EXHAUSTED when `available <= 0`
    - Test: session remains ACTIVE when `available > 0`
    - Test: in-flight reservations for session are not modified when session becomes EXHAUSTED
    - _Requirements: 9.1, 9.3_

- [ ] 5. Checkpoint — Ensure domain layer tests pass
  - Run `cd agent-guard && PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/test_enforcement_phase4.py -q`
  - Ensure all domain-layer tests pass before proceeding to gateway wiring.

- [ ] 6. Wire enforcement into the gateway endpoint in `backend/app/api/v1/router.py`
  - [ ] 6.1 Add budget account resolution helper inside the gateway handler
    - After identity validation, look up `BudgetAccount` rows for `team_id`, `agent_id`, and `session_id`; collect their IDs into `account_ids`
    - If any account is missing, return HTTP 402 with detail indicating which scope lacks a budget account
    - _Requirements: 1.1, 10.1_
  - [ ] 6.2 Insert reservation call before the provider invocation
    - Call `atomic_reserve(db, account_ids, estimated_cost, request_id, team_id, agent_id, session_id)` within an explicit `async with db.begin()` block
    - If `atomic_reserve` returns `False`, return HTTP 402 without calling the provider
    - Commit the reservation transaction before `provider.generate()` is called
    - _Requirements: 1.5, 2.1, 2.2, 2.3, 10.2, 10.3_
  - [ ] 6.3 Add warning check after successful reservation
    - Instantiate `BudgetWarningService` and call `check_and_emit(db, accounts, policies)` after the reservation commits
    - Load `BudgetPolicy` rows for the applicable entities to pass threshold configuration
    - _Requirements: 7.1, 10.1_
  - [ ] 6.4 Wire settle, release, and mark-unknown into the provider-call try/except block
    - On provider success: call `atomic_settle(db, account_ids, estimated_cost, actual_cost, request_id)` in a new `async with db.begin()` block before `persist_usage`
    - On `RuntimeError` (provider error): call `atomic_release(db, account_ids, estimated_cost, request_id)` in a new `async with db.begin()` block; then return HTTP 502
    - On `asyncio.TimeoutError`: call `mark_unknown(db, request_id)` in a new `async with db.begin()` block; then return HTTP 504
    - _Requirements: 3.1, 4.1, 5.1, 10.4, 10.5, 10.6_
  - [ ] 6.5 Add session exhaustion check after settlement
    - After `persist_usage`, call `SessionExhaustionService.check_and_close(db, session_id)`
    - _Requirements: 9.1, 10.1_
  - [ ] 6.6 Add `reservation_id` to `GatewayChatResponse` schema in `backend/app/api/v1/schemas.py`
    - Add `reservation_id: str` field to `GatewayChatResponse`; populate it with `request_id` in the response construction
    - _Requirements: 10.7_

- [ ] 7. Implement `ReservationRecoveryService` in `backend/app/domain/recovery.py`
  - [ ] 7.1 Create `backend/app/domain/recovery.py` with `ReservationRecoveryService` class
    - Implement `recover_stale(db, staleness_minutes)` async method
    - Query `Reservation` rows with `state == RESERVED` and `created_at < now() - timedelta(minutes=staleness_minutes)` using `SELECT ... FOR UPDATE SKIP LOCKED`
    - For each stale reservation, set `state = UNKNOWN` (do NOT modify `reserved_amount`)
    - Return list of affected reservation IDs
    - _Requirements: 6.1, 6.2_
  - [ ] 7.2 Register background recovery task in `backend/app/main.py`
    - Use FastAPI lifespan (`asynccontextmanager`) or `@app.on_event("startup")` to start an `asyncio.create_task` loop
    - Loop: sleep `settings.RESERVATION_RECOVERY_INTERVAL_MINUTES * 60` seconds, then call `recover_stale`
    - Log recovered reservation IDs at INFO level
    - _Requirements: 6.1, 6.4_
  - [ ]* 7.3 Write unit tests for `ReservationRecoveryService` in `backend/tests/test_enforcement_phase4.py`
    - **Property 8: Stale recovery marks only old reservations UNKNOWN**
    - Test: reservations older than threshold → state becomes UNKNOWN, reserved_amount unchanged
    - Test: reservations younger than threshold → state remains RESERVED
    - Test: SETTLED and RELEASED reservations are not modified by recovery
    - _Requirements: 6.1, 6.2_

- [ ] 8. Checkpoint — Ensure full test suite passes
  - Run `cd agent-guard && PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/ -q`
  - All Phase 2, Phase 3, and Phase 4 unit tests must pass before concurrency tests.

- [ ] 9. Write gateway integration tests in `backend/tests/test_enforcement_phase4.py`
  - [ ] 9.1 Integration test: successful reservation and settlement flow
    - Set up real in-memory SQLite (or test PostgreSQL) with team/agent/session/budget accounts and pricing
    - POST to `/gateway/chat/completions`; verify: HTTP 200, `Reservation.state == SETTLED`, `settled_spend` increased, `reserved_amount` decreased
    - _Requirements: 1.3, 3.1, 3.2, 10.1_
  - [ ] 9.2 Integration test: HTTP 402 on insufficient budget
    - Set `budget_limit` to less than estimated cost; verify HTTP 402 and no reservation row created
    - _Requirements: 1.4, 2.1, 2.2, 2.3_
  - [ ] 9.3 Integration test: HTTP 502 → reservation RELEASED
    - Use `simulate_error="provider_error"`; verify HTTP 502 and `Reservation.state == RELEASED`
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ] 9.4 Integration test: HTTP 504 → reservation UNKNOWN
    - Use `simulate_error="timeout"` with `GATEWAY_TIMEOUT_SECONDS=0.001`; verify HTTP 504 and `Reservation.state == UNKNOWN`; verify `reserved_amount` unchanged on accounts
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 9.5 Integration test: session becomes EXHAUSTED when budget consumed
    - Set session `budget_limit` to exactly the estimated cost of one request; run one request; verify `session.status == EXHAUSTED`; run second request; verify HTTP 403
    - _Requirements: 9.1, 9.2_
  - [ ]* 9.6 Write property test for reservation-settlement accounting in `backend/tests/test_enforcement_properties.py`
    - **Property 2: Successful reservation increments all accounts**
    - **Property 4: Reservation–settlement conservation**
    - Using `hypothesis`: generate random `budget_limit`, `settled_spend`, `estimated_cost`, `actual_cost` values; run reserve then settle; verify conservation identity holds
    - _Requirements: 1.3, 3.1, 3.2_
  - [ ]* 9.7 Write property test for idempotent settlement in `backend/tests/test_enforcement_properties.py`
    - **Property 5: Idempotent settlement**
    - Using `hypothesis`: generate a settled reservation; call `atomic_settle` again; verify all account values unchanged
    - _Requirements: 3.3_
  - [ ]* 9.8 Write property test for hard-block correctness in `backend/tests/test_enforcement_properties.py`
    - **Property 3: Insufficient budget leaves accounts unmodified**
    - Using `hypothesis`: generate account states where at least one is insufficient; verify `atomic_reserve` returns False and no account is modified
    - _Requirements: 1.4, 2.3_

- [ ] 10. Write concurrency tests in `backend/tests/test_enforcement_concurrency.py`
  - [ ] 10.1 Concurrent reservation test: no overspend on shared team budget
    - Using `asyncio.gather`: launch 10 concurrent requests all targeting the same team budget account sized for 3 requests
    - Verify: exactly 3 succeed (HTTP 200), remaining 7 are rejected (HTTP 402), and final `settled_spend` does not exceed `budget_limit`
    - _Requirements: 1.1, 8.3, 11.1, 11.3_
  - [ ]* 10.2 Write property test for concurrency no-overspend in `backend/tests/test_enforcement_properties.py`
    - **Property 1: No overspend under concurrent reservations**
    - Using `hypothesis` + `asyncio.gather`: generate budget sizes and concurrency counts; verify aggregate committed never exceeds `budget_limit`
    - _Requirements: 1.1, 11.1_

- [ ] 11. Final checkpoint — Full test suite green
  - Run `cd agent-guard && PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests/ -v`
  - Ensure all tests pass. Ask the user if any test failures arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery.
- Each task references specific requirements for traceability; requirement numbers correspond to `requirements.md` section numbers (e.g. `1.3` = Requirement 1, Acceptance Criterion 3).
- `atomic_reserve` and `atomic_settle` are refactored to remove internal commits; the gateway manages transaction boundaries using `async with db.begin()`.
- The `hypothesis` library must be added to `backend/requirements.txt` before property tests can run (`hypothesis>=6.100.0`).
- Apply the Alembic migration (`alembic upgrade head` from the `backend/` directory) before running integration tests against a real PostgreSQL instance.
- The `BudgetAccount` for each entity (team/agent/session) is identified by the entity's own ID (existing convention in the codebase).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "4.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5", "6.6", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 7, "tasks": ["9.6", "9.7", "9.8", "10.1"] },
    { "id": 8, "tasks": ["10.2"] }
  ]
}
```
