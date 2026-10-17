# Domain, Ownership, and Versioning

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define canonical models and authoritative owners.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Aggregates

Institution, Course/CourseVersion/SourceArtifact, ContentPackage/CTF/TeachingGraph/LessonPlan/KnowledgeIndex, Class/RuntimeSessionPlan/ClassroomSession, Student/Enrollment/Progress, VoiceAuthorization.

## Ownership

Compiler owns Content IR; Publication Service owns immutable package relationships; Classroom Actor owns active state; Teacher Orchestrator owns pedagogical proposals; PostgreSQL-equivalent owns durable records; event log owns ordered history; Redis is projection/cache; search is rebuildable.

## Runtime tuple

Course, CTF, content package, lesson, optional teaching graph, assessment, knowledge index, policy, model-routing configuration, and home region are explicit versions. `latest` is forbidden.

## Implemented tuple

The tuple is implemented in `backend/app/classroom/` (`service.py`, `repository.py`, `catalog.py`, `snapshot.py`) behind `POST /classes/{classId}/start`, with scheduling (`POST /classes`), the session and its pinned tuple (`GET /classes/{classId}`), the durable snapshot (`GET /classes/{classId}/snapshot`) and join authorization against the class enrollment (`POST /classes/{classId}/bootstrap-token`). Scheduling records intent and pins nothing; the **start** resolves the tuple exactly once and writes it into an immutable `RuntimeSessionPlan`, which is the strongest form of "`latest` is forbidden": after the start transaction no code path asks a publication question again, because the session reads its own plan. Every member is a resolved value — course/version/`publication_id`/`package_id`/`content_package_version`/`content_digest`, lesson plan version, the knowledge-index pin *and the content that pin is compatible with* (`DEC-DATA-005`), an optional `teaching_graph_version`, policy, capability and home region — with `assessment_version`/`model_routing_version` pinned as explicit nulls, because the canonical tuple names them and V0 has neither subsystem; naming the absence means the immutable tuple never has to gain a field later. A class started with no version named takes the course's *current* publication at start; publishing a correction afterwards leaves the running session's tuple and snapshot byte-identical and a later class pins the newer version (`DEC-CONTENT-005`). The policy/region/capability half comes from a replaceable `RuntimeCatalog` (its versioned defaults and the configured home region) and from the *observed* identity of the warmed default renderer (`name@version`, full identity recorded in the plan's `capabilities`), so no cloud region is assumed (`DEC-TECH-009` is `OPEN`) and a later renderer upgrade cannot retroactively change what a session warmed.

The transition is `SCHEDULED -> PREPARING -> ACTIVE` and `PREPARING` is **in-process only and never persisted**, exactly as `SEALING`/`INDEXING`/`COMMITTING` are for publication: the plan, the session, the initial snapshot and the class's state change commit in one transaction, so a crash mid-start leaves the class `SCHEDULED` and retryable rather than a half-pinned session — a partial start is invisible by construction. A refusal is classified as `CLASS_NOT_READY` with a precise `issue_code` (`VERSION_NOT_PUBLISHED`, `INCOMPATIBLE_INDEX`, `INCOMPATIBLE_CONTENT`, `CONTENT_DIGEST_MISMATCH`, `WRONG_STATE`, `COMMIT_CONFLICT`) and writes nothing; the start re-verifies the pinned package against its seal before pinning it and never parses the source document (`DEC-CONTENT-001`). The identity of a start is the class, so a repeated or concurrent start returns the first session with `created: false` (`DEC-RUNTIME-003`). The initial snapshot is durable and validated (schema version *and* checksum) before use, so a damaged snapshot is refused rather than replayed (`DEC-DATA-004`); the session pins the initial `actor_epoch` and a join credential binds it, so a stale epoch cannot authorize (`DEC-RUNTIME-007`), while claiming/transferring ownership across an actor failure remains V1-002's. A join credential is issued only to an enrolled student of a running class, is stored as a digest, and carries `subscribe` scope only (`DEC-TURN-001`: group student microphones are unpublished by default); the ordered per-class event log and its outbox are `DEC-DATA-003`'s open technology and V1-002's, so a start records state, snapshot and telemetry rather than emitting an event.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-TURN-001`
- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-004`
- `DEC-DATA-005`
- `DEC-RELIABILITY-002`
- `DEC-DEPLOY-002`
