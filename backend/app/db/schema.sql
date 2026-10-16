-- Mentora durable store, SQLite dialect.
--
-- DEC-DATA-001: PostgreSQL "or equivalent durable relational store" owns durable
-- institutional/course/publication records. SQLite is the V0 local/dev equivalent;
-- the schema is written so the repository layer can target PostgreSQL later.
--
-- Every tenant-owned row carries institution_id and every query is tenant-scoped.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS institutions (
    institution_id TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    course_id      TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL REFERENCES institutions(institution_id),
    title          TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_courses_institution ON courses(institution_id);

-- DEC-CONTENT-005: published artifacts are immutable; versions are explicit.
CREATE TABLE IF NOT EXISTS course_versions (
    version_id     TEXT PRIMARY KEY,
    course_id      TEXT NOT NULL REFERENCES courses(course_id),
    institution_id TEXT NOT NULL,
    version        INTEGER NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (course_id, version)
);
CREATE INDEX IF NOT EXISTS idx_course_versions_tenant ON course_versions(institution_id, course_id);

CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id    TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    course_id      TEXT NOT NULL REFERENCES courses(course_id),
    version_id     TEXT NOT NULL REFERENCES course_versions(version_id),
    filename       TEXT NOT NULL,
    media_type     TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    byte_size      INTEGER NOT NULL,
    object_key     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    -- Idempotent duplicate upload: same bytes in a course resolve to one artifact.
    UNIQUE (institution_id, course_id, sha256)
);
CREATE INDEX IF NOT EXISTS idx_source_artifacts_tenant ON source_artifacts(institution_id, course_id);

CREATE TABLE IF NOT EXISTS compiler_jobs (
    job_id         TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    artifact_id    TEXT NOT NULL UNIQUE REFERENCES source_artifacts(artifact_id),
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    institution_id  TEXT NOT NULL,
    scope           TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    artifact_id     TEXT NOT NULL REFERENCES source_artifacts(artifact_id),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (institution_id, scope, idempotency_key)
);

-- V0-007: teacher review. A decision and a draft are *state about* a package,
-- never content of it: the immutable package is untouched by either
-- (DEC-CONTENT-005) and drafts are append-only revisions, so a proposed edit
-- can never overwrite anything (docs/architecture/07_PUBLICATION_AND_REVIEW.md:
-- "Corrections create new versions").

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id    TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    artifact_id    TEXT NOT NULL REFERENCES source_artifacts(artifact_id),
    version_id     TEXT NOT NULL REFERENCES course_versions(version_id),
    package_id     TEXT NOT NULL,
    -- A decision binds to the content it reviewed, so a rebuild under different
    -- content/compiler/renderer configuration makes it stale rather than current.
    content_package_version TEXT NOT NULL,
    decision       TEXT NOT NULL,
    reason         TEXT,
    reviewer       TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_decisions_tenant
    ON review_decisions(institution_id, artifact_id, created_at);

CREATE TABLE IF NOT EXISTS review_drafts (
    draft_id       TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    artifact_id    TEXT NOT NULL REFERENCES source_artifacts(artifact_id),
    version_id     TEXT NOT NULL REFERENCES course_versions(version_id),
    package_id     TEXT NOT NULL,
    content_package_version TEXT NOT NULL,
    lesson_plan_version TEXT,
    revision       INTEGER NOT NULL,
    sections       TEXT NOT NULL,
    edited_by      TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    -- Revisions are append-only: the unique key is what makes a concurrent save
    -- fail loudly instead of silently branching the history.
    UNIQUE (artifact_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_review_drafts_tenant
    ON review_drafts(institution_id, artifact_id, revision);
