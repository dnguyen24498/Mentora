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

-- V0-008: atomic publication. A publication is an immutable *fact* — this course
-- version, this content package, this pinned version tuple, published once — so
-- these tables are append-only apart from the supersede link. Publication state
-- is written by exactly one transaction (PublicationRepository.commit), which is
-- why a half-published version cannot be observed.

-- The knowledge-index version a published content version pins (DEC-DATA-005).
-- The index *content* is V0-014; the identity and its provenance are recorded
-- here, before anything can retrieve through the pin.
CREATE TABLE IF NOT EXISTS knowledge_index_versions (
    index_version_id        TEXT PRIMARY KEY,
    institution_id          TEXT NOT NULL,
    course_id               TEXT NOT NULL REFERENCES courses(course_id),
    version_id              TEXT NOT NULL REFERENCES course_versions(version_id),
    package_id              TEXT NOT NULL,
    content_package_version TEXT NOT NULL,
    index_version           TEXT NOT NULL,
    status                  TEXT NOT NULL,
    -- The published content this identity is compatible with (the seal digest).
    source_digest           TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    -- One index version per published content version: a retry cannot fork the
    -- identity that retrieval filters by.
    UNIQUE (institution_id, version_id, content_package_version)
);
CREATE INDEX IF NOT EXISTS idx_index_versions_tenant
    ON knowledge_index_versions(institution_id, version_id);

CREATE TABLE IF NOT EXISTS publications (
    publication_id          TEXT PRIMARY KEY,
    institution_id          TEXT NOT NULL,
    course_id               TEXT NOT NULL REFERENCES courses(course_id),
    version_id              TEXT NOT NULL REFERENCES course_versions(version_id),
    -- Denormalised version number: the supersede rule and "newest" ordering need
    -- it without a join, and it is what the pinned tuple reports.
    course_version          INTEGER NOT NULL,
    artifact_id             TEXT NOT NULL REFERENCES source_artifacts(artifact_id),
    package_id              TEXT NOT NULL,
    content_package_version TEXT NOT NULL,
    lesson_plan_versions    TEXT NOT NULL,
    knowledge_index_version TEXT NOT NULL,
    teaching_graph_version  TEXT,
    index_version_id        TEXT NOT NULL REFERENCES knowledge_index_versions(index_version_id),
    -- The seal: manifest identity plus the content digest a read can re-check.
    manifest_sha256         TEXT NOT NULL,
    content_digest          TEXT NOT NULL,
    file_count              INTEGER NOT NULL,
    total_bytes             INTEGER NOT NULL,
    state                   TEXT NOT NULL,
    -- Set on a superseded publication. A link, never a delete: a session pinned
    -- to it keeps reading it (DEC-CONTENT-005).
    superseded_by           TEXT,
    published_by            TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    -- Idempotency: the same version published with the same content is one
    -- publication (DEC-RUNTIME-003); a correction has a new course version.
    UNIQUE (institution_id, version_id, content_package_version)
);
CREATE INDEX IF NOT EXISTS idx_publications_tenant
    ON publications(institution_id, course_id, created_at);
CREATE INDEX IF NOT EXISTS idx_publications_version
    ON publications(institution_id, version_id);

-- Transactional outbox (docs/architecture/16_DATA_STORAGE_AND_EVENTS.md): the
-- event row commits with the publication, so metadata and event cannot disagree.
-- Delivered at least once, consumers deduplicate event_id; delivery itself is not
-- implemented (DEC-TECH-001 ordered-event technology is OPEN), so dispatched_at
-- stays NULL until a later task adds a sender.
CREATE TABLE IF NOT EXISTS publication_outbox (
    event_id       TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id   TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    dispatched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_publication_outbox_tenant
    ON publication_outbox(institution_id, created_at);

-- V0-009: class and runtime session plan. ``docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md``:
-- a class pins an explicit runtime tuple — *"Course, CTF, content package, lesson,
-- optional teaching graph, assessment, knowledge index, policy, model-routing
-- configuration, and home region are explicit versions. ``latest`` is forbidden."*
-- The plan and the snapshot are append-only facts: there is no UPDATE path to a
-- pinned tuple, so a running session cannot be moved onto different content
-- (``DEC-CONTENT-005``: "active sessions pin all compatible versions").

-- A scheduled teaching occurrence. Scheduling records the *intent*; it pins the
-- version tuple only when it starts, and then once for the life of the session.
CREATE TABLE IF NOT EXISTS classes (
    class_id       TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL REFERENCES institutions(institution_id),
    course_id      TEXT NOT NULL REFERENCES courses(course_id),
    title          TEXT NOT NULL,
    -- The course version the teacher pinned when scheduling, if any. NULL means
    -- "resolve the course's current published version once, at start" — a single
    -- recorded decision, never a runtime ``latest`` lookup.
    version_id     TEXT REFERENCES course_versions(version_id),
    scheduled_for  TEXT,
    state          TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    started_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_classes_tenant ON classes(institution_id, course_id);

-- Who may join. Authorization is class participation, not tenant membership:
-- a principal inside the tenant that is not enrolled is refused (403
-- ``NOT_ENROLLED``), which is what "only authorized enrollment can join" means in
-- V0, where institutional federation/roles do not exist yet.
CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id  TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    class_id       TEXT NOT NULL REFERENCES classes(class_id),
    student_id     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    -- Enrolling twice is one enrollment, so a retried command is not an error.
    UNIQUE (institution_id, class_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_enrollments_tenant
    ON enrollments(institution_id, class_id);

-- The pinned runtime tuple (terminology: ``RuntimeSessionPlan``), written once at
-- start. Every column is the *resolved* value: no column is a pointer that a
-- later publication could move.
CREATE TABLE IF NOT EXISTS runtime_session_plans (
    session_plan_id         TEXT PRIMARY KEY,
    institution_id          TEXT NOT NULL,
    class_id                TEXT NOT NULL REFERENCES classes(class_id),
    course_id               TEXT NOT NULL REFERENCES courses(course_id),
    version_id              TEXT NOT NULL REFERENCES course_versions(version_id),
    course_version          INTEGER NOT NULL,
    publication_id          TEXT NOT NULL REFERENCES publications(publication_id),
    package_id              TEXT NOT NULL,
    content_package_version TEXT NOT NULL,
    -- The seal's content digest: what the pinned bytes are, re-checkable later.
    content_digest          TEXT NOT NULL,
    lesson_plan_version     TEXT NOT NULL,
    knowledge_index_version TEXT NOT NULL,
    index_version_id        TEXT NOT NULL REFERENCES knowledge_index_versions(index_version_id),
    -- The index pin's compatibility basis: a plan whose pin does not match this
    -- content is refused rather than retrieved through (DEC-DATA-005).
    index_source_digest     TEXT NOT NULL,
    teaching_graph_version  TEXT,
    -- Named absences: the canonical tuple lists assessment and model-routing, and
    -- V0 has neither subsystem. They are recorded as explicit NULLs so the
    -- immutable tuple never has to gain a field later.
    assessment_version      TEXT,
    model_routing_version   TEXT,
    policy_version          TEXT NOT NULL,
    capability_version      TEXT NOT NULL,
    capabilities            TEXT NOT NULL,
    region                  TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    -- One plan per class: a retry cannot fork the tuple a session runs on.
    UNIQUE (class_id)
);
CREATE INDEX IF NOT EXISTS idx_session_plans_tenant
    ON runtime_session_plans(institution_id, class_id);

CREATE TABLE IF NOT EXISTS classroom_sessions (
    session_id      TEXT PRIMARY KEY,
    institution_id  TEXT NOT NULL,
    class_id        TEXT NOT NULL REFERENCES classes(class_id),
    course_id       TEXT NOT NULL REFERENCES courses(course_id),
    session_plan_id TEXT NOT NULL REFERENCES runtime_session_plans(session_plan_id),
    state           TEXT NOT NULL,
    -- Initial epoch; ownership transfer/fencing across an actor move is V1-002.
    actor_epoch     INTEGER NOT NULL,
    state_version   INTEGER NOT NULL,
    event_sequence  INTEGER NOT NULL,
    snapshot_id     TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    -- "Unique constraints enforce one live session" (DATA_MODEL_AND_TRANSACTIONS).
    UNIQUE (class_id)
);
CREATE INDEX IF NOT EXISTS idx_classroom_sessions_tenant
    ON classroom_sessions(institution_id, class_id);

-- The durable initial snapshot (DEC-DATA-004). Recovery replays from a snapshot,
-- so it is validated (schema version + checksum) before it is used.
CREATE TABLE IF NOT EXISTS session_snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    session_id     TEXT NOT NULL REFERENCES classroom_sessions(session_id),
    class_id       TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    state          TEXT NOT NULL,
    state_version  INTEGER NOT NULL,
    event_sequence INTEGER NOT NULL,
    actor_epoch    INTEGER NOT NULL,
    document       TEXT NOT NULL,
    checksum       TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    -- One snapshot per state version: re-snapshotting the same version is a retry,
    -- not a new fact.
    UNIQUE (session_id, state_version)
);
CREATE INDEX IF NOT EXISTS idx_session_snapshots_tenant
    ON session_snapshots(institution_id, session_id);

-- Short-lived join credentials. Only the digest is stored — the token is a
-- credential, so a database read must not yield a usable one — and every token
-- has a terminal path (expiry, or ``revoked_at``).
CREATE TABLE IF NOT EXISTS bootstrap_tokens (
    token_sha256   TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL,
    class_id       TEXT NOT NULL REFERENCES classes(class_id),
    session_id     TEXT NOT NULL REFERENCES classroom_sessions(session_id),
    student_id     TEXT NOT NULL,
    actor_epoch    INTEGER NOT NULL,
    nonce          TEXT NOT NULL,
    scopes         TEXT NOT NULL,
    issued_at      TEXT NOT NULL,
    expires_at     TEXT NOT NULL,
    revoked_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_bootstrap_tokens_tenant
    ON bootstrap_tokens(institution_id, class_id);

