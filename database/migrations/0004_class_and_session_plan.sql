-- PostgreSQL reference implementation of the V0-009 class and session tables.
-- Technology decision remains governed by ADR (DEC-DATA-001: "PostgreSQL or
-- equivalent durable relational store"); SQLite is the V0 local/dev equivalent
-- (backend/app/db/schema.sql) and the repository layer targets both.
--
-- These tables are the durable half of class start
-- (docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md:
-- SCHEDULED -> PREPARING -> ACTIVE) and of the pinned runtime tuple
-- (docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md: "Course, CTF, content
-- package, lesson, optional teaching graph, assessment, knowledge index, policy,
-- model-routing configuration, and home region are explicit versions. `latest`
-- is forbidden.").
--
-- PREPARING is deliberately *not* a stored state: the plan, the session, the
-- initial snapshot and the class's state change commit in one transaction, so an
-- interrupted start leaves the class SCHEDULED and retryable rather than a
-- half-pinned session. "Unique constraints enforce one live session"
-- (docs/data/DATA_MODEL_AND_TRANSACTIONS.md) is the UNIQUE (class_id) below.

CREATE TABLE classes (
    class_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL,
    course_id      uuid NOT NULL REFERENCES courses(course_id),
    title          varchar(512) NOT NULL,
    version_id     uuid REFERENCES course_versions(version_id),
    scheduled_for  timestamptz,
    state          varchar(16) NOT NULL
        CHECK (state IN ('SCHEDULED', 'ACTIVE', 'DEGRADED', 'RECOVERING', 'ENDING', 'COMPLETED', 'FAILED')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    started_at     timestamptz
);
CREATE INDEX classes_tenant_idx ON classes(institution_id, course_id);

CREATE TABLE enrollments (
    enrollment_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL,
    class_id       uuid NOT NULL REFERENCES classes(class_id),
    student_id     varchar(256) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (institution_id, class_id, student_id)
);
CREATE INDEX enrollments_tenant_idx ON enrollments(institution_id, class_id);

CREATE TABLE runtime_session_plans (
    session_plan_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id          uuid NOT NULL,
    class_id                uuid NOT NULL REFERENCES classes(class_id),
    course_id               uuid NOT NULL REFERENCES courses(course_id),
    version_id              uuid NOT NULL REFERENCES course_versions(version_id),
    course_version          integer NOT NULL,
    publication_id          uuid NOT NULL REFERENCES publications(publication_id),
    package_id              varchar(128) NOT NULL,
    content_package_version varchar(128) NOT NULL,
    content_digest          char(64) NOT NULL,
    lesson_plan_version     varchar(128) NOT NULL,
    knowledge_index_version varchar(128) NOT NULL,
    index_version_id        uuid NOT NULL REFERENCES knowledge_index_versions(index_version_id),
    -- The index pin's compatibility basis: a plan whose pin does not match this
    -- content is refused rather than retrieved through (DEC-DATA-005).
    index_source_digest     char(64) NOT NULL,
    teaching_graph_version  varchar(128),
    -- Named absences (assessment and model-routing do not exist in V0), recorded
    -- so the immutable tuple never has to gain a field later.
    assessment_version      varchar(128),
    model_routing_version   varchar(128),
    policy_version          varchar(128) NOT NULL,
    capability_version      varchar(128) NOT NULL,
    capabilities            jsonb NOT NULL,
    region                  varchar(64) NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (class_id)
);
CREATE INDEX runtime_session_plans_tenant_idx
    ON runtime_session_plans(institution_id, class_id);

CREATE TABLE classroom_sessions (
    session_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id  uuid NOT NULL,
    class_id        uuid NOT NULL REFERENCES classes(class_id),
    course_id       uuid NOT NULL REFERENCES courses(course_id),
    session_plan_id uuid NOT NULL REFERENCES runtime_session_plans(session_plan_id),
    state           varchar(16) NOT NULL
        CHECK (state IN ('SCHEDULED', 'ACTIVE', 'DEGRADED', 'RECOVERING', 'ENDING', 'COMPLETED', 'FAILED')),
    actor_epoch     integer NOT NULL,
    state_version   integer NOT NULL,
    event_sequence  integer NOT NULL,
    snapshot_id     uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz NOT NULL,
    -- "Unique constraints enforce one live session" (DATA_MODEL_AND_TRANSACTIONS).
    UNIQUE (class_id)
);
CREATE INDEX classroom_sessions_tenant_idx ON classroom_sessions(institution_id, class_id);

CREATE TABLE session_snapshots (
    snapshot_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL,
    session_id     uuid NOT NULL REFERENCES classroom_sessions(session_id),
    class_id       uuid NOT NULL,
    schema_version varchar(64) NOT NULL,
    state          varchar(16) NOT NULL,
    state_version  integer NOT NULL,
    event_sequence integer NOT NULL,
    actor_epoch    integer NOT NULL,
    document       jsonb NOT NULL,
    checksum       char(64) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- Re-snapshotting the same state version is a retry, not a new fact.
    UNIQUE (session_id, state_version)
);
CREATE INDEX session_snapshots_tenant_idx ON session_snapshots(institution_id, session_id);

CREATE TABLE bootstrap_tokens (
    token_sha256   char(64) PRIMARY KEY,
    institution_id uuid NOT NULL,
    class_id       uuid NOT NULL REFERENCES classes(class_id),
    session_id     uuid NOT NULL REFERENCES classroom_sessions(session_id),
    student_id     varchar(256) NOT NULL,
    actor_epoch    integer NOT NULL,
    nonce          varchar(64) NOT NULL,
    scopes         jsonb NOT NULL,
    issued_at      timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz NOT NULL,
    revoked_at     timestamptz
);
CREATE INDEX bootstrap_tokens_tenant_idx ON bootstrap_tokens(institution_id, class_id);
