-- PostgreSQL reference implementation of the V0-007 teacher-review tables.
-- Technology decision remains governed by ADR (DEC-DATA-001: "PostgreSQL or
-- equivalent durable relational store"); SQLite is the V0 local/dev equivalent
-- (backend/app/db/schema.sql) and the repository layer targets both.
--
-- A review decision and a draft lesson order are *state about* a package, never
-- content of it: the immutable package (DEC-CONTENT-005) is untouched by either,
-- and draft revisions are append-only.

CREATE TABLE review_decisions (
    decision_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id          uuid NOT NULL,
    artifact_id             uuid NOT NULL REFERENCES source_artifacts(artifact_id),
    version_id              uuid NOT NULL REFERENCES course_versions(version_id),
    package_id              varchar(128) NOT NULL,
    content_package_version varchar(128) NOT NULL,
    decision                varchar(16) NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
    reason                  text,
    reviewer                varchar(256) NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX review_decisions_tenant_idx
    ON review_decisions(institution_id, artifact_id, created_at DESC);

CREATE TABLE review_drafts (
    draft_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id          uuid NOT NULL,
    artifact_id             uuid NOT NULL REFERENCES source_artifacts(artifact_id),
    version_id              uuid NOT NULL REFERENCES course_versions(version_id),
    package_id              varchar(128) NOT NULL,
    content_package_version varchar(128) NOT NULL,
    lesson_plan_version     varchar(128),
    revision                integer NOT NULL CHECK (revision > 0),
    sections                jsonb NOT NULL,
    edited_by               varchar(256) NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (artifact_id, revision)
);
CREATE INDEX review_drafts_tenant_idx
    ON review_drafts(institution_id, artifact_id, revision DESC);
