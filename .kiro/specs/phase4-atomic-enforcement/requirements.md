# Requirements Document

## Introduction

Phase 4 adds atomic budget enforcement to the AgentGuard LLM gateway. Before any provider call, the gateway must atomically reserve the estimated maximum cost across all applicable budget accounts (team, agent, session). After the provider responds, it settles actual cost and releases the unused reservation. The phase also covers idempotent settlement, timeout recovery, 80% utilization warnings, 100% hard-block rejection, and automatic session closure when a session budget is exhausted. Phases 0–3 are complete; this phase wires enforcement into the existing gateway endpoint and adds the necessary supporting infrastructure.

## Glossary

- **BudgetAccount**: A row in `budget_accounts` tracking `budget_limit`, `settled_spend`, and `reserved_amount` for a team, agent, or session entity.
- **Reservation**: A row in `reservations` representing a hold on estimated cost, identified by `request_id`. Follows the state machine: RESERVED → SETTLED | RELEASED | UNKNOWN.
- **committed**: `settled_spend + reserved_amount` for a given BudgetAccount.
- **available**: `budget_limit - committed` for a given BudgetAccount.
- **EnforcementService**: The domain component responsible for atomic reserve, settle, release, and mark-unknown operations.
- **BudgetWarningService**: The component that emits at-most-one `BudgetWarningEvent` per account per budget window when utilization reaches the warning threshold.
- **SessionExhaustionService**: The component that transitions a session to EXHAUSTED status when its BudgetAccount is fully consumed.
- **ReservationRecoveryService**: The background component that marks stale RESERVED reservations as UNKNOWN for safe reconciliation.
- **window_key**: A string that uniquely identifies a budget window for warning deduplication (e.g. `"2025-01"` for a monthly window, the session ID for a session-lifetime window).
- **Gateway**: The FastAPI endpoint `POST /api/v1/gateway/chat/completions`.
- **Provider**: An `AbstractLLMProvider` implementation (MockLLMProvider in tests).
- **estimated_cost**: Maximum cost reserved before the provider call, calculated from input token count and `max_output_tokens`.
- **actual_cost**: Final cost calculated from provider-reported token usage after the call completes.

---

## Requirements

### Requirement 1: Atomic Multi-Level Reservation

**User Story:** As the AgentGuard gateway, I want to atomically reserve estimated cost across all applicable budget accounts before making a provider call, so that concurrent requests cannot collectively exceed any configured limit.

#### Acceptance Criteria

1. WHEN the Gateway receives a valid chat completion request, THE EnforcementService SHALL attempt to lock all applicable BudgetAccount rows (team, agent, and session accounts) in ascending ID order within a single database transaction before invoking the Provider.
2. WHEN locking BudgetAccount rows, THE EnforcementService SHALL acquire row-level locks using `SELECT ... FOR UPDATE` ordered by account ID to prevent deadlocks across concurrent requests.
3. WHEN all locked BudgetAccounts have `available >= estimated_cost`, THE EnforcementService SHALL increment `reserved_amount` by `estimated_cost` on every applicable account and insert a Reservation row with `state = RESERVED` in the same transaction.
4. WHEN any locked BudgetAccount has `available < estimated_cost`, THE EnforcementService SHALL reject the reservation, leave all accounts unmodified, and not create a Reservation row.
5. THE EnforcementService SHALL commit the reservation transaction before the Provider is called, ensuring no database transaction remains open during Provider inference.

---

### Requirement 2: Pre-Call Rejection on Insufficient Budget

**User Story:** As an operator, I want the gateway to reject requests that cannot fit within any applicable budget before the provider is called, so that no cost is incurred for requests that would exceed a limit.

#### Acceptance Criteria

1. WHEN the EnforcementService cannot reserve funds due to insufficient budget on any applicable account, THE Gateway SHALL return HTTP 402 with a detail message identifying the exhausted scope (team, agent, or session).
2. WHEN the Gateway returns HTTP 402, THE Gateway SHALL NOT invoke the Provider.
3. WHEN the Gateway returns HTTP 402, THE Gateway SHALL NOT create a Reservation row or modify any BudgetAccount.

---

### Requirement 3: Idempotent Settlement After Provider Success

**User Story:** As the AgentGuard gateway, I want to settle the actual cost after a successful provider call in a way that is safe to retry, so that a process crash between provider completion and settlement does not cause double-charging.

#### Acceptance Criteria

1. WHEN the Provider call succeeds, THE EnforcementService SHALL execute a settlement transaction that locks the Reservation row and all applicable BudgetAccount rows in ascending ID order.
2. WHEN settling, THE EnforcementService SHALL decrement `reserved_amount` by `estimated_cost` and increment `settled_spend` by `actual_cost` on every applicable account, and set `reservation.state = SETTLED` and `reservation.actual_cost = actual_cost`.
3. WHEN `atomic_settle` is called with a `request_id` whose Reservation already has `state = SETTLED`, THE EnforcementService SHALL perform no changes and return successfully (idempotent).
4. IF `atomic_settle` is called with a `request_id` whose Reservation has `state = RELEASED` or `state = UNKNOWN`, THEN THE EnforcementService SHALL raise an `InvalidStateTransitionError` without modifying any row.

---

### Requirement 4: Reservation Release on Confirmed Provider Failure

**User Story:** As the AgentGuard gateway, I want to release a reservation when the provider returns a confirmed error, so that the reserved budget is returned and future requests are not unnecessarily blocked.

#### Acceptance Criteria

1. WHEN the Provider raises a `RuntimeError` (confirmed provider error with no charge), THE EnforcementService SHALL execute a release transaction that decrements `reserved_amount` by `estimated_cost` on every applicable account and sets `reservation.state = RELEASED`.
2. WHEN releasing a Reservation, THE EnforcementService SHALL NOT modify `settled_spend`.
3. WHEN releasing a Reservation, THE Gateway SHALL return HTTP 502 to the client.

---

### Requirement 5: UNKNOWN State on Timeout

**User Story:** As the AgentGuard gateway, I want to mark a reservation UNKNOWN on a provider timeout rather than releasing it, so that the system does not silently absorb charges if the provider actually processed the request.

#### Acceptance Criteria

1. WHEN the Provider call raises `asyncio.TimeoutError`, THE EnforcementService SHALL transition `reservation.state` from RESERVED to UNKNOWN without modifying `reserved_amount` on any account.
2. WHILE a Reservation is in state UNKNOWN, THE EnforcementService SHALL NOT release `reserved_amount` from the applicable BudgetAccounts.
3. WHEN marking a Reservation UNKNOWN, THE Gateway SHALL return HTTP 504 to the client.

---

### Requirement 6: Stale Reservation Recovery

**User Story:** As an operator, I want stale RESERVED reservations left by crashed processes to be automatically moved to UNKNOWN, so that they can be safely reconciled rather than silently blocking budget forever.

#### Acceptance Criteria

1. THE ReservationRecoveryService SHALL periodically query for Reservation rows with `state = RESERVED` and `created_at` older than a configurable staleness threshold (default: 60 minutes).
2. WHEN stale RESERVED reservations are found, THE ReservationRecoveryService SHALL transition each to `state = UNKNOWN` without modifying `reserved_amount`.
3. THE staleness threshold SHALL be configurable via `Settings.RESERVATION_STALENESS_MINUTES`.
4. THE recovery polling interval SHALL be configurable via `Settings.RESERVATION_RECOVERY_INTERVAL_MINUTES`.

---

### Requirement 7: 80% Utilization Warning

**User Story:** As an operator, I want to receive a warning when any applicable budget account reaches 80% utilization, so that I can take action before the budget is exhausted.

#### Acceptance Criteria

1. WHEN a Reservation is created and the resulting `committed / budget_limit` for any applicable BudgetAccount meets or exceeds `policy.warning_threshold_pct / 100`, THE BudgetWarningService SHALL check whether a `BudgetWarningEvent` already exists for that `(account_id, window_key)`.
2. WHEN no existing `BudgetWarningEvent` exists for the `(account_id, window_key)`, THE BudgetWarningService SHALL insert one recording the `account_id`, `threshold_pct`, `utilization_pct`, and `window_key`.
3. WHEN a `BudgetWarningEvent` already exists for the `(account_id, window_key)`, THE BudgetWarningService SHALL NOT insert a duplicate.
4. THE `window_key` for a MONTHLY budget SHALL be formatted as `"YYYY-MM"` based on the UTC timestamp of the reservation.
5. THE `window_key` for a SESSION_LIFETIME budget SHALL be the `session_id`.

---

### Requirement 8: 100% Hard-Block Enforcement

**User Story:** As an operator, I want all requests that would exceed any applicable budget to be hard-blocked before the provider is called, so that budget limits are strictly enforced regardless of concurrency.

#### Acceptance Criteria

1. THE EnforcementService SHALL enforce hard limits by checking `available >= estimated_cost` for every applicable account within the same locked transaction as the reservation, with no grace period beyond the configured limit.
2. WHEN a request is hard-blocked, THE Gateway SHALL return HTTP 402 before the Provider is invoked.
3. WHEN multiple concurrent requests race against a nearly-exhausted budget, THE EnforcementService SHALL allow at most one to succeed such that the resulting `committed` does not exceed `budget_limit`.

---

### Requirement 9: Session Closure on Budget Exhaustion

**User Story:** As an operator, I want sessions whose budget is fully consumed to be automatically closed, so that subsequent requests against that session are rejected without attempting a reservation.

#### Acceptance Criteria

1. WHEN a Reservation is settled and the session's BudgetAccount has `available <= 0` after settlement, THE SessionExhaustionService SHALL set `session.status = EXHAUSTED`.
2. WHEN a session has `status = EXHAUSTED`, THE Gateway SHALL reject new chat completion requests for that session with HTTP 403 (this is handled by the existing identity validation which already rejects non-ACTIVE sessions).
3. WHEN a session's status transitions to EXHAUSTED, THE SessionExhaustionService SHALL NOT cancel or modify in-flight reservations for that session.

---

### Requirement 10: Gateway Wiring

**User Story:** As a developer, I want the existing gateway endpoint to enforce all budget rules in the correct sequence, so that every provider call is preceded by a successful reservation and followed by settlement or release.

#### Acceptance Criteria

1. THE Gateway SHALL enforce the following sequence: identity validation → pricing resolution → reservation → warning check → provider call → settlement or release or mark-unknown → usage persistence → session exhaustion check.
2. THE Gateway SHALL NOT call the Provider before `atomic_reserve` returns `True`.
3. WHEN `atomic_reserve` returns `False`, THE Gateway SHALL return HTTP 402 without calling the Provider.
4. WHEN the Provider call succeeds, THE Gateway SHALL call `atomic_settle` before returning the response to the client.
5. WHEN the Provider call raises `RuntimeError`, THE Gateway SHALL call `atomic_release` and return HTTP 502.
6. WHEN the Provider call raises `asyncio.TimeoutError`, THE Gateway SHALL call `mark_unknown` and return HTTP 504.
7. THE Gateway response body SHALL include `reservation_id` (the `request_id`) so clients can correlate budget decisions.

---

### Requirement 11: Concurrency Correctness

**User Story:** As an operator, I want the system to remain correct under concurrent requests from multiple agents sharing a budget, so that no combination of parallel calls can collectively overspend any applicable budget.

#### Acceptance Criteria

1. WHEN multiple concurrent requests target the same BudgetAccount, THE EnforcementService SHALL serialize access via row-level locks such that the aggregate reserved and settled amounts never exceed `budget_limit`.
2. WHEN a deadlock would occur, THE EnforcementService SHALL rely on consistent ascending ID ordering of lock acquisition to prevent it.
3. THE concurrency tests SHALL execute at least 10 simultaneous reservation attempts against a budget sized for fewer than 10 to verify that no overspend occurs.
