# V0-008: Atomic publication and index version

**Week:** W4  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Publish immutable package and compatible knowledge-index identity.

## Dependencies

- V0-006
- V0-007

## Requirement IDs

- `DEC-CONTENT-005`
- `DEC-DATA-005`
- `DEC-RUNTIME-003`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/PUBLICATION_STATE_MACHINE.md`
- `docs/architecture/07_PUBLICATION_AND_REVIEW.md`
- `docs/data/OUTBOX_SNAPSHOT_AND_RETENTION.md`

## In Scope

- Approve/seal/index/commit state flow.
- Immutable package storage.
- Knowledge-index version record.
- Transactional publication metadata/outbox.
- Published version retrieval.

## Out of Scope

- Full semantic index content.
- LMS notification.

## Acceptance Criteria

- Partial failure never exposes published version.
- Published bytes cannot be overwritten.
- Correction creates new version.

## Required Tests

- Crash between stages, duplicate publish, index failure, checksum failure, read old version.

## Files/Areas Allowed to Change

- `backend/app/publication/`
- `workers/`
- `database/`
- `tests/integration/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

**Link to commit/PR:** `<filled by the follow-up record commit>`

**What was built.** `app/publication/service.py`, `seal.py`, `index.py`, `outbox.py`
and `errors.py`; `models.py`/`repository.py`/`telemetry.py` extended; four routes
(`POST /course-versions/{id}/publish`, `GET /course-versions/{id}/publication`,
`GET /publications/{id}`, `GET /courses/{id}/publications`); three tables
(`publications`, `knowledge_index_versions`, `publication_outbox`) in
`app/db/schema.sql` with `database/migrations/0003_atomic_publication.sql` as the
PostgreSQL reference; `contracts/openapi/openapi.yaml` and
`contracts/events/course-version-published.schema.json`.

**How each acceptance criterion is met.**

| Criterion | Mechanism |
| --- | --- |
| Partial failure never exposes published version | `SEALING` / `INDEXING` / `COMMITTING` are in-process stages and are **never persisted**: there is no staging row, so a crash at any point leaves no visible half-publication. All writes (index record, publication row, outbox row, the guarded `APPROVED → PUBLISHED` update, the supersede links) happen in **one** transaction in `PublicationRepository.commit`. |
| Published bytes cannot be overwritten | Publishing **writes no object-store bytes at all** — the package is content-addressed and owned by the compiler; the transition only *pins* the prefix. A correction changes the source, hence the version, hence the prefix. The seal makes a later overwrite *observable*: `?verify=true` re-reads the pinned prefix and reports `MISMATCH`. |
| Correction creates new version | A corrected upload is a new course version with its own package and publication; publishing it marks the course's strictly older publications (and any other publication of the same version) `SUPERSEDED` with a `superseded_by` link. Nothing is deleted — a pinned session keeps reading the old one (`DEC-CONTENT-005`). |

**Design decisions worth stating.**

- **The three stages run before a single commit, and the stages are named but not
  stored** (`PUBLICATION_STAGE_SEALING/INDEXING/COMMITTING` are telemetry labels,
  not rows). This is what makes "invisible" a structural property instead of a
  rollback/compensation path.
- **Sealing computes two digests.** `manifest_sha256` is the envelope (kept for
  provenance); `content_digest` is path + SHA-256 of every manifest-listed file,
  sorted, and is the *verify* basis — so a legitimate rewrite of the manifest (a
  new `created_at`) is not reported as tampering.
- **The index stage is a replaceable interface, and the baseline builds no
  content.** `BaselineIndexBuilder` returns the package's own declared
  `knowledge_index_version` (`"unindexed"`, status `UNINDEXED`) and records the
  published `content_digest` as the content it is compatible with
  (`DEC-DATA-005`). Choosing a vector store or writing embeddings would present
  `DEC-TECH-008` as decided; V0-014 replaces the builder without moving the record,
  the pin, or the transaction.
- **Idempotency first, then the approval check.** The identity is
  `(version_id, content_package_version)`, unique per tenant. The existence check
  runs *before* the approval precondition because a replay arrives when the version
  is already `PUBLISHED`, which is not `APPROVED`; running the precondition first
  would turn every legitimate replay into a `WRONG_STATE` refusal. A lost race on
  the commit (`CommitConflict`) re-reads the winner and returns it.
- **Refusals are classified and write nothing.** `409 PUBLICATION_BLOCKED` with
  `issue_code` `NOT_APPROVED` (`STALE_APPROVAL` names the "approved for different
  content" case), `WRONG_STATE`, the validator's own code (e.g.
  `CHECKSUM_MISMATCH`), or `INDEX_FAILED`. No new `ErrorCode` member was added —
  the existing envelope already carries `issue_code`.
- **Tenant scoping.** An institution's version is denied `403 TENANT_ACCESS_DENIED`
  like any other version read; a publication of another institution is `404`, not
  `403`, because the lookup is tenant-scoped and does not need to leak existence.
- **No dispatcher.** The outbox row commits with the publication, is pull-readable
  and has `dispatched_at` null: delivery technology is `OPEN` (`DEC-TECH-001`), so
  nothing here pretends to send it.

**Test command and result.**

```
cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q
→ 383 passed, 1 warning in 75.01s   (was 364; +19 in tests/test_publication_publish.py)
```

`tests/test_publication_publish.py` (19 tests) covers the five required tests —
**crash between stages** (a failing commit, a failing index builder, a checksum
failure; each asserts *nothing* is published and the retry then succeeds),
**duplicate publish**, **index failure**, **checksum failure**, **read old version**
— plus the happy path and its reads, the index pin and its provenance, the outbox
event validated against its JSON-Schema contract, a **concurrent** duplicate
publish (one commit, one replay), the approval precondition (absent / rejected /
stale), publishing writing no object-store bytes, a correction leaving the old
package readable with both verifiable, tamper detection, tenant isolation, and
telemetry. Frontend: no change (`npx tsc --noEmit` clean, 38 vitest tests pass).

**Demo (real reference deck, 16.7 MB, 28 slides).** Driven end to end against a
throwaway data dir with the real code and object store:

```
upload              202  artifact c5096d06-…, version 1a2a85ae-…
review-package      200  pkg-fd40e629ab70765e  publishable=true  READY  (build+render 2.1s)
decision            200  APPROVED, stale=false
publish             200  created=true  PUBLISHED  course_version=1
                          file_count=57  total_bytes=36,542,049
                          knowledge_index_version="unindexed"
                          manifest_sha256=a4b1163d…  content_digest=0e483792…
publish again       200  created=false  same publication_id            (idempotent)
read by version/id  200  same publication
history             200  1 publication
verify (intact)     200  integrity VERIFIED (observed == expected digest)
overwrite an asset, verify again
                    200  integrity MISMATCH  CHECKSUM_MISMATCH  (published record unchanged)
publish as university-002
                    403  TENANT_ACCESS_DENIED
rows: publications 1 (PUBLISHED) · knowledge_index_versions 1 (UNINDEXED,
      source_digest == content_digest) · publication_outbox 1
      (course.version.published, dispatched_at NULL) · course_versions 1 (PUBLISHED)
```

**Metrics observed.** One publish emits three `publication.stage` records
(`SEALED`/`INDEXED`/`COMMITTED`) and one `publication.published`; counters
`stages_sealed`/`stages_indexed`/`stages_committed` = 1 and
`publications_created` = 1, with `publications_replayed` / `publications_blocked` = 0.
A refused publish emits `publication.blocked` with the stage and `issue_code` and
increments the stage's failure counter. A verified read emits
`publication.integrity_checked`. Records carry the tenant, version, artifact,
package and pinned tuple — never slide text, notes or a review reason, which
`test_publication_telemetry_carries_identities_not_content` asserts.

**Traceability rows added.** `governance/TRACEABILITY_MATRIX.csv`:
`DEC-CONTENT-005` ← `seal.py`, `service.py`, `tests/test_publication_publish.py`;
`DEC-DATA-005` ← `index.py`, `repository.py`, `service.py`, the test;
`DEC-RUNTIME-003` ← `repository.py`, `service.py`, the test;
`DEC-DATA-004` ← `outbox.py`, the event contract, the test;
`DEC-DATA-001` ← `database/migrations/0003_atomic_publication.sql`;
`DEC-RELIABILITY-002` ← `errors.py`, `service.py`, the test.

**Known limitations.**

- The index version is an **identity only**; no index content is built. Retrieval
  cannot answer anything until V0-014 replaces `BaselineIndexBuilder`.
- The outbox is **not dispatched** — there is no sender, and delivery technology is
  `OPEN` (`DEC-TECH-001`). At-least-once delivery and consumer dedup are designed
  for (the contract says consumers dedup on `event_id`) but not implemented.
- The stage sequence is **in-process, not resumable**: a process crash between
  stages simply restarts the request, and the transition is short and idempotent, so
  that is the deliberate V0 shape (`DEC-TECH-003` durable workflow is `OPEN`). A
  long index build (V0-014) will need a checkpointed job of its own.
- Integrity verification is **structural**: no SVG rasterizer is available, so
  "the bytes are the published bytes" is asserted over file digests, not over
  rendered pixels.
- `published_by` is **attribution, not authorization** — identity and roles are not
  implemented (`docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`), so it cannot
  stop an unauthorized caller today.
- `knowledge_index_version` on the publication is the value the package manifest
  *declares*, while the pinned record's `index_version` comes from the builder.
  Sealing already refuses a package whose manifest declares none
  (`MISSING_KNOWLEDGE_INDEX_VERSION`), so on the baseline path the two are the same
  string by construction; V0-014 must keep the builder's answer in step with the
  manifest, or retrieval would pin an identity the package never declared.

