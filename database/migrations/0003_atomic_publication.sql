-- PostgreSQL reference implementation of the V0-008 publication tables.
-- Technology decision remains governed by ADR (DEC-DATA-001: "PostgreSQL or
-- equivalent durable relational store"); SQLite is the V0 local/dev equivalent
-- (backend/app/db/schema.sql) and the repository layer targets both.
--
-- These tables are the durable half of the atomic publication transition
-- (docs/state-machines/PUBLICATION_STATE_MACHINE.md:
-- APPROVED -> SEALING -> INDEXING -> COMMITTING -> PUBLISHED -> SUPERSEDED).
--
-- Two properties are encoded in the constraints rather than trusted to
-- application code:
--   * a publication is written exactly once, by one transaction, so a partially
--     published version cannot be observed (nothing here is a "staging" row);
--   * (version, content_package_version) is unique, which is what makes a
--     duplicate publish idempotent instead of a second publication
--     (DEC-RUNTIME-003), and one index version per published content version,
--     which is what retrieval pins (DEC-DATA-005).

CREATE TABLE knowledge_index_versions (
    index_version_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id          uuid NOT NULL,
    course_id               uuid NOT NULL REFERENCES courses(course_id),
    version_id              uuid NOT NULL REFERENCES course_versions(version_id),
    package_id              varchar(128) NOT NULL,
    content_package_version varchar(128) NOT NULL,
    index_version           varchar(128) NOT NULL,
    status                  varchar(32) NOT NULL,
    source_digest           char(64) NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (institution_id, version_id, content_package_version)
);
CREATE INDEX knowledge_index_versions_tenant_idx
    ON knowledge_index_versions(institution_id, version_id);

CREATE TABLE publications (
    publication_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id          uuid NOT NULL,
    course_id               uuid NOT NULL REFERENCES courses(course_id),
    version_id              uuid NOT NULL REFERENCES course_versions(version_id),
    course_version          integer NOT NULL,
    artifact_id             uuid NOT NULL REFERENCES source_artifacts(artifact_id),
    package_id              varchar(128) NOT NULL,
    content_package_version varchar(128) NOT NULL,
    lesson_plan_versions    jsonb NOT NULL,
    knowledge_index_version varchar(128) NOT NULL,
    teaching_graph_version  varchar(128),
    index_version_id        uuid NOT NULL REFERENCES knowledge_index_versions(index_version_id),
    manifest_sha256         char(64) NOT NULL,
    content_digest          char(64) NOT NULL,
    file_count              integer NOT NULL,
    total_bytes             bigint NOT NULL,
    state                   varchar(16) NOT NULL CHECK (state IN ('PUBLISHED', 'SUPERSEDED')),
    superseded_by           uuid REFERENCES publications(publication_id),
    published_by            varchar(256) NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (institution_id, version_id, content_package_version)
);
CREATE INDEX publications_tenant_idx ON publications(institution_id, course_id, created_at);
CREATE INDEX publications_version_idx ON publications(institution_id, version_id);

CREATE TABLE publication_outbox (
    event_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id  uuid NOT NULL,
    aggregate_type  varchar(64) NOT NULL,
    aggregate_id    uuid NOT NULL,
    event_type      varchar(128) NOT NULL,
    payload         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    dispatched_at   timestamptz
);
CREATE INDEX publication_outbox_tenant_idx ON publication_outbox(institution_id, created_at);
