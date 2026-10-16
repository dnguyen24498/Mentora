"""SQLite connection handling and migration application.

The reference schema in ``database/migrations/0001_baseline.sql`` is PostgreSQL;
this module owns the SQLite-equivalent DDL used for local/dev/tests.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(database_path: Path | str) -> sqlite3.Connection:
    """Open a connection with foreign keys on and row access by name."""

    path = Path(database_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(database_path: Path | str) -> None:
    """Apply the schema. Safe to run against an empty or existing database."""

    conn = connect(database_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction so a failure leaves no partial writes.

    Durable state/artifact creation commits atomically
    (``docs/data/DATA_MODEL_AND_TRANSACTIONS.md``).
    """

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
