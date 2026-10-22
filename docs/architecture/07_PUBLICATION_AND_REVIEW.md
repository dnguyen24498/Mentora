# Publication, Review, and Teacher Studio

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define approval policy and atomic visibility.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Review outcomes are auto-allowed, human-required, or blocked. Conflicting notes/source, meaning-affecting degradation, unsupported reveal, AI assessments, weak evidence, regulated content, and executable content trigger review/block according to policy.

Atomic publication validates references/schemas/checksums/provenance, writes immutable package, builds compatible pinned index, commits metadata/outbox, then exposes the version. Corrections create new versions.

## Implemented transition

The transition is implemented in `backend/app/publication/` (`service.py`, `seal.py`, `index.py`, `outbox.py`, `repository.py`) behind `POST /course-versions/{versionId}/publish`, with retrieval by version, by publication id and by course (`?verify=true` re-checks a pinned package and reports `VERIFIED`/`MISMATCH`/`MISSING` rather than failing). It never writes a package: the compiler already wrote the bytes and the transition only *pins* them, which is what makes "published bytes cannot be overwritten" a property of the publication rather than of a write path.

The stages `SEALING`, `INDEXING` and `COMMITTING` are **in-process only and never persisted**: there is no staging row, so a crash at any stage leaves no half-published version to clean up — "partial publication is invisible" holds by construction rather than by compensation. **Sealing** re-validates the stored package (checksums, references, schema) and records two digests: `manifest_sha256` (the envelope, kept for provenance) and `content_digest` (path + SHA-256 of every listed file, sorted — the *verify* basis, so a legitimate manifest rewrite like a new `created_at` is not a false alarm). **Indexing** goes through the replaceable `IndexBuilder` interface: the baseline builder establishes the index-version *identity* a publication must pin (`DEC-DATA-005`) and builds no index content — a Baseline Content Package is usable without enrichment (`DEC-CONTENT-002`) and the search/vector technology is `OPEN` (`DEC-TECH-008`), so it pins `unindexed` and records the published `content_digest` as the content it is compatible with; V0-014 replaces the builder without moving the record or the atomicity. **Committing** is one transaction that writes the index-version row, the publication row and the transactional-outbox row, performs the guarded `APPROVED → PUBLISHED` status change and marks superseded publications — so a visible publication always has its index pin and its event.

A publication's identity is `(version_id, content_package_version)` and is unique per tenant: a retry after a lost response returns the *same* publication with `created: false`, and two concurrent requests for one version produce exactly one publication (the loser re-reads the winner), which is `DEC-RUNTIME-003` at the transition's boundary. A **correction is a new course version** with a new package and a new publication; publishing it marks the course's strictly older publications, and any other publication of the same version, `SUPERSEDED` with a `superseded_by` link — never deleted, because `DEC-CONTENT-005` pins all compatible versions and a session that started on the older one keeps reading it. A publication whose approval no longer covers the content that would go out (`STALE_APPROVAL`), that was never approved (`NOT_APPROVED`), or whose package or index cannot be established is refused *before* the transaction with `PUBLICATION_BLOCKED` plus a precise `issue_code` and writes nothing, leaving the version retryable. The outbox row is written but not dispatched: delivery technology is `OPEN` (`DEC-TECH-001`), so `dispatched_at` stays null until a later task adds a sender.

## Upload shortcut

`POST /artifacts/{artifactId}/auto-publish` composes the same stages for the
Library upload flow, so an ordinary deck does not need three manual actions
(build → approve → publish) before it can be taught. It is not a bypass of the
policy:

* the package is built through the normal review projection, so a blocking
  fidelity failure is still refused before any decision exists;
* only a package whose state is `READY` (auto-allowed, `requires_review=false`)
  is approved automatically, with the uploading teacher's attribution, and then
  published atomically as that teacher;
* a `REVIEW_REQUIRED` package is returned **unpublished** with its review state,
  so a human-required deck still needs a teacher's decision in Teacher Studio;
* the action requires `content:write`, `review:write` and `publication:write`
  together — an institution administrator cannot compose it — and replaying it
  for the same content returns the existing publication with `created: false`.

Attribution (`published_by`, the review decision's `reviewer`) is the signed-in
teacher's account, falling back to the tenant for the pre-auth development
shortcut. It is an audit attribution, not an authorization control.

## Locked Decisions Implemented

- `DEC-CONTENT-005`
- `DEC-CONTENT-008`
- `DEC-DATA-005`
