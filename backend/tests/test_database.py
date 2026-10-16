from app.db.database import init_db, transaction


def _table_names(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_init_db_creates_all_tables(conn):
    assert {
        "institutions",
        "courses",
        "course_versions",
        "source_artifacts",
        "compiler_jobs",
        "idempotency_records",
    } <= _table_names(conn)


def test_init_db_is_idempotent(settings):
    init_db(settings.database_path)
    init_db(settings.database_path)  # must not raise


def test_transaction_rolls_back_on_error(conn):
    conn.execute(
        "INSERT INTO institutions (institution_id, name, created_at) VALUES ('i', 'n', 't')"
    )
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO courses (course_id, institution_id, title, created_at) "
                "VALUES ('c', 'i', 'x', 't')"
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert conn.execute("SELECT COUNT(*) AS n FROM courses").fetchone()["n"] == 0
