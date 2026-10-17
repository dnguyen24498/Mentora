# AI Prompt for V0-020

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth.
3. State transitions and invariants.
4. Failure, timeout, retry, cancellation, fallback, and recovery paths.
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted.
- Do not introduce a new service, database, broker, or framework without an accepted ADR.
- Update contracts before changing interfaces.
- Keep domain logic independent from provider SDKs.
- Add structured telemetry and update traceability.
- Stop if source-of-truth files conflict.

## Analysis plan (returned for this task)

1. **Requirements / LOCKED decisions.** `DEC-DATA-001` gives the durable
   relational store ownership of durable truth, so a request that reports success
   must have committed exactly its own state; `DEC-RELIABILITY-001`/`002` require
   bounded failure and integrity rather than an unbounded, corrupting failure
   mode. No renderer, provider or technology choice is touched, so no OPEN
   decision is affected.
2. **Ownership boundary.** `app/db/database.py` owns connection lifecycle and the
   `transaction()` helper; repositories own SQL; `app/api/app.py` owns wiring. The
   fix stays in the first and third — repositories keep calling `self._conn.execute(...)`
   and `transaction(self._conn)` unchanged.
3. **Invariants.** (a) Any transaction is confined to one request's thread and
   commits/rolls back atomically. (b) A cursor is only consumed by the thread that
   created it. (c) Two concurrent writers serialize instead of interleaving. (d)
   A repository built from a plain `sqlite3.Connection` (tests, single-threaded
   callers) keeps working.
4. **Failure / timeout / recovery.** Concurrency is not a random failure to retry:
   the failure mode must be removed. Write contention between connections is
   handled by SQLite's `busy_timeout` (bounded wait) so a writer queues rather
   than raising `database is locked`; that is the bounded-failure path. The
   `transaction()` helper still rolls back on any exception.
5. **Exact files.** `backend/app/db/database.py`, `backend/app/api/app.py`,
   `backend/tests/test_database_concurrency.py`, `backend/README.md`,
   traceability rows.
6. **Tests.** Written first and observed failing against the shared-connection
   wiring (concurrent API reads+writes), then passing after the change, plus a
   `Database` contract test (one connection per thread, reused within a thread).
7. **Blockers / contradictions.** None. `FND-001` (no CI) means the suite is run
   manually; PostgreSQL remains the production target, so this is a V0/dev fix
   and must not be read as accepting SQLite.
