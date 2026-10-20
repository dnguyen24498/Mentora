"""V0-020: request-scoped database access.

FastAPI runs sync endpoints in a worker threadpool, so more than one request is
in flight at a time. If every one of them shares a single ``sqlite3.Connection``,
their transactions and cursors interleave on it: ``BEGIN IMMEDIATE`` raises
*"cannot start a transaction within a transaction"*, a cursor being consumed
collides with another thread's statement (*"another row available"*), and — worse
than noise — a transaction can be committed with another request's statements
mixed in, which violates a foreign key. These tests hold the contract that makes
concurrent use safe.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.courses.repository import CourseRepository
from app.db.database import Database

INSTITUTION = "university-001"
HEADERS = {"X-Institution-Id": INSTITUTION}
THREADS = 8
ROUNDS = 6


def _client(settings) -> TestClient:
    # `raise_server_exceptions=False`: a handler error must be observed as the
    # 5xx a real client would see, not as an exception inside the test thread.
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.fixture
def settings(dev_settings):
    """This suite drives the pre-identity V0 API as a teacher, so it opts into the
    development tenant shortcut (V0-023). The shipped default requires a session on
    every route; that locked default is covered by ``tests/test_required_sign_in.py``.
    """

    return dev_settings


def test_concurrent_reads_and_writes_all_succeed(settings):
    """240 concurrent read+write requests: every one succeeds, nothing is lost."""

    with _client(settings) as client:

        def call(index: int) -> list[int]:
            created = client.post("/courses", params={"title": f"Course {index}"}, headers=HEADERS)
            listed = client.get("/courses", headers=HEADERS)
            return [created.status_code, listed.status_code]

        with ThreadPoolExecutor(max_workers=THREADS) as pool:
            results = list(pool.map(call, range(THREADS * ROUNDS)))

    codes = Counter(code for per_call in results for code in per_call)
    assert set(codes) == {200, 201}, dict(codes)

    # A lost or partially applied transaction would show up here.
    listed = client.get("/courses", headers=HEADERS).json()
    assert len(listed) == THREADS * ROUNDS
    assert {course["title"] for course in listed} == {
        f"Course {index}" for index in range(THREADS * ROUNDS)
    }


def test_concurrent_transactions_stay_atomic(settings):
    """Each thread's transaction commits its own rows, and only its own."""

    database = Database(settings.database_path)
    repository = CourseRepository(database)
    repository.ensure_institution(INSTITUTION)
    repository.ensure_institution("university-002")

    def worker(index: int) -> None:
        # `create_course` wraps its INSERT in `transaction()`; interleaving must
        # not be able to attach it to another thread's transaction.
        repository.create_course(INSTITUTION, f"A {index}")
        repository.create_course("university-002", f"B {index}")

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        list(pool.map(worker, range(THREADS * ROUNDS)))

    first = repository.list_courses(INSTITUTION)
    second = repository.list_courses("university-002")
    assert len(first) == THREADS * ROUNDS
    assert len(second) == THREADS * ROUNDS
    # Tenant scoping is not a side effect of sharing a connection.
    assert {course.title for course in first} == {f"A {i}" for i in range(THREADS * ROUNDS)}
    assert {course.title for course in second} == {f"B {i}" for i in range(THREADS * ROUNDS)}


def test_the_database_reuses_a_connection_within_a_thread(settings):
    database = Database(settings.database_path)

    assert database.connection is database.connection
    assert database.execute("SELECT 1").fetchone()[0] == 1


def test_the_database_gives_concurrent_threads_their_own_connection(settings):
    database = Database(settings.database_path)
    main_connection = database.connection

    with ThreadPoolExecutor(max_workers=4) as pool:
        per_thread = list(pool.map(lambda _index: database.connection, range(4)))

    assert all(connection is not main_connection for connection in per_thread)
    assert len({id(connection) for connection in per_thread}) == 4
    # ...and each of them is usable after the work that created it is done.
    for connection in per_thread:
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] >= 0


def test_the_database_sets_a_busy_timeout(settings):
    """Concurrent writers queue instead of failing with ``database is locked``."""

    database = Database(settings.database_path)

    assert database.connection.execute("PRAGMA busy_timeout").fetchone()[0] > 0
