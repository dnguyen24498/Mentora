"""SQLite connection handling and migration application.

The reference schema in ``database/migrations/0001_baseline.sql`` is PostgreSQL;
this module owns the SQLite-equivalent DDL used for local/dev/tests.

Concurrency model
-----------------
The API serves its synchronous endpoints from a worker threadpool, so several
requests are handled at the same time. A ``sqlite3.Connection`` is *not* safe to
share for that: transaction state (``BEGIN IMMEDIATE`` ... ``COMMIT``) and
statement cursors are connection-scoped, so two requests using one connection
interleave — one request's ``BEGIN`` lands inside another's transaction, a
cursor is consumed while another thread runs a statement on the same connection,
and a transaction can be committed with foreign statements attached to it.

:class:`Database` therefore hands every thread its own connection, which is also
what makes a transaction request-scoped. Writers between connections serialize on
SQLite's write lock, bounded by ``PRAGMA busy_timeout`` so a queued writer waits
instead of failing with ``database is locked``.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

#: How long a blocked writer waits for the write lock before giving up. Bounded
#: on purpose (``DEC-RELIABILITY-001``): contention queues briefly, then fails
#: visibly rather than hanging a request forever.
DEFAULT_BUSY_TIMEOUT_MS = 5000


def connect(
    database_path: Path | str, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
) -> sqlite3.Connection:
    """Open a connection with foreign keys on and row access by name."""

    path = Path(database_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Order matters: the timeout must be in place before the pragmas that can
    # need the database lock (e.g. switching to WAL for the first time).
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


class Database:
    """Thread-scoped SQLite connections for one database file.

    Every thread that touches the database gets its own connection, created on
    first use and reused for that thread. Callers keep writing
    ``database.execute(...)`` and ``transaction(database)``: the two entry points
    repositories use, so a repository does not need to know which connection it
    is talking to.
    """

    def __init__(
        self, database_path: Path | str, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    ) -> None:
        self.path = Path(database_path)
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()

    @property
    def connection(self) -> sqlite3.Connection:
        """The calling thread's connection, opening it on first use."""

        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = connect(self.path, busy_timeout_ms=self.busy_timeout_ms)
            self._local.connection = connection
        return connection

    def execute(
        self, sql: str, parameters: "tuple | list" = ()
    ) -> sqlite3.Cursor:
        """Execute on the calling thread's connection (real cursor returned)."""

        return self.connection.execute(sql, parameters)

    def executescript(self, script: str) -> sqlite3.Cursor:
        return self.connection.executescript(script)

    def close(self) -> None:
        """Close (and drop) this thread's connection; other threads are untouched."""

        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None


def init_db(database_path: Path | str) -> None:
    """Apply the schema. Safe to run against an empty or existing database."""

    conn = connect(database_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()


@contextmanager
def transaction(conn: "Database | sqlite3.Connection") -> Iterator["Database | sqlite3.Connection"]:
    """Explicit transaction so a failure leaves no partial writes.

    Durable state/artifact creation commits atomically
    (``docs/data/DATA_MODEL_AND_TRANSACTIONS.md``). The transaction runs on the
    calling thread's connection, so concurrent requests cannot share one
    (``DEC-DATA-001``: the durable store owns the truth).
    """

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
