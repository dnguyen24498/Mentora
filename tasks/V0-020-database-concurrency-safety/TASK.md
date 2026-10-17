# V0-020: Request-scoped database access (concurrency safety)

**Week:** W4  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the API safe under concurrent requests. Today `create_app` opens **one**
`sqlite3.Connection` and every repository shares it. FastAPI runs sync endpoints
in a worker threadpool, so two in-flight requests use that one connection at the
same time and their transactions and cursors interleave. Observed live
(`GET /courses` → `500`) and reproduced deterministically under load:

| error | count (240 concurrent requests) |
| --- | --- |
| `sqlite3.OperationalError: cannot start a transaction within a transaction` | 64 |
| `sqlite3.InterfaceError: bad parameter or other API misuse` | 19 |
| `sqlite3.OperationalError: cannot commit - no transaction is active` | 18 |
| `sqlite3.DatabaseError: no more rows available` / `another row available` | 11 |
| `sqlite3.IntegrityError: FOREIGN KEY constraint failed` | 3 |

130 of 240 requests returned `500` (both reads and writes). The `FOREIGN KEY`
and cursor errors show this is **state integrity**, not just noise: a transaction
can be committed with statements from another request interleaved into it.

The fix is per-thread connections (one per request-serving thread) plus a busy
timeout so writers queue instead of failing. No new dependency, no new store.

## Dependencies

- V0-001 (course/source-artifact persistence)
- V0-004 (extraction service)
- V0-007 (review decisions/drafts are durable state)

## Requirement IDs

- `DEC-DATA-001` (the durable relational store owns durable truth)
- `DEC-RELIABILITY-001` (deadline/bounded retry/fallback rather than unbounded failure)
- `DEC-RELIABILITY-002` (bounded failure and state integrity)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `backend/app/db/database.py`, `backend/app/api/app.py`
- `backend/app/courses/repository.py` (the repository call pattern)
- `docs/data/DATA_MODEL_AND_TRANSACTIONS.md`
- `AGENTS.md` ("Backend persistence note")

## Scope

- `app/db/database.py`: add `Database`, a thread-scoped connection provider, and
  a `busy_timeout` on every connection.
- `app/api/app.py`: wire `Database` instead of a single `connect(...)` result.
- `backend/tests/test_database_concurrency.py`: a regression test that hammers the
  API with concurrent reads and writes and asserts no `5xx` and no lost rows,
  plus a focused `Database` contract test.
- `backend/README.md`: document the connection model.

## Out of scope

- Replacing SQLite (PostgreSQL is the production target per `DEC-DATA-001`; the
  SQLite store is the documented V0/dev equivalent).
- Connection pooling with recycling/limits beyond the threadpool's thread count.
- Changing any endpoint contract or the `transaction()` helper's signature.

## Acceptance criteria

- Concurrent read+write requests through the API never return `5xx`.
- Every request that reports success is durably visible afterwards (no lost or
  partially applied transaction).
- A single-threaded request that begins a transaction is still atomic
  (`transaction()` semantics unchanged).
- `env -u PYTHONPATH .venv/bin/python -m pytest -q` stays green.

## Completion Evidence

**Reported symptom.** On the running dev server, `GET /courses` returned
`500 Internal Server Error` immediately after an application (re)start.

**Root cause.** `create_app` opened **one** `sqlite3.Connection` and shared it
with every repository, while FastAPI serves synchronous endpoints from a worker
threadpool. A `sqlite3.Connection` is not safe to share that way: transaction
state (`BEGIN IMMEDIATE` … `COMMIT`) and statement cursors are connection-scoped,
so two in-flight requests interleave them.

**Reproduced before the fix** (240 concurrent read+write requests against the
API):

| outcome | count |
| --- | --- |
| `201` / `200` | 19 / 48 |
| `500` | 28 |
| `404` (`get_course` after a rolled-back INSERT) | 1 |
| courses actually persisted | 23 of 48 |

Server-side exception types: `cannot start a transaction within a transaction`
(64), `bad parameter or other API misuse` (19), `cannot commit - no transaction is
active` (18), `no more rows available` / `another row available` (11),
`FOREIGN KEY constraint failed` (3). The last two are **state integrity**, not
noise: a transaction could be committed with another request's statements
attached to it.

**Fix.** `app/db/database.py` gains `Database`, which gives each thread its own
connection (created on first use, reused for that thread) and exposes the two
entry points repositories already used (`execute`, plus the unchanged
`transaction()` helper) — so no repository changed. Every connection now sets
`PRAGMA busy_timeout = 5000`, so concurrent writers queue for SQLite's write lock
(bounded wait) instead of failing with `database is locked`. `create_app` wires
`Database` instead of a bare connection. No new dependency; PostgreSQL remains the
production target (`DEC-DATA-001`).

**After the fix**, the same 240-request load: **120 × 200 + 120 × 201, 0 × 5xx,
0 exceptions, 120 of 120 courses persisted**. On the reporter's own live server
(with the change hot-reloaded): 120 concurrent requests → 120 × 200.

**Tests.** `backend/tests/test_database_concurrency.py` (5 new): concurrent API
reads+writes all succeed and nothing is lost; concurrent transactions stay atomic
and tenant-scoped; `Database` reuses a connection within a thread and gives
concurrent threads distinct, usable connections; a busy timeout is set.

`env -u PYTHONPATH .venv/bin/python -m pytest -q` → **310 passed** (was 305).

**Commit:** `cb6a955`.

