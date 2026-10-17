# Baseline Content Package — Layout and Reference Rules

**Status:** Implemented contract (V0-006)  
**Owners:** Content Compiler (`backend/app/compiler/package_builder/`)  
**Schemas:** `contracts/ctf/manifest.schema.json`, `scene.schema.json`, `lesson-plan.schema.json`

A **Baseline Content Package** is the immutable envelope produced by the baseline
builder stage of `docs/architecture/04_CONTENT_COMPILER.md`
(`… → Content IR → baseline builder → … → validation`). It is the artifact the
runtime consumes — it is **not** the internal Content IR, and it never contains a
source document.

The three schemas above define the *shape* of the documents. This file defines
what the schemas deliberately leave open: the package's path layout, its
reference rules, and the manifest's role as the commit point.

---

## Normative language

**MUST**, **MUST NOT**, **SHOULD**, and **MAY** are requirements.

## 1. Package root

A package is a namespaced prefix in object storage (V0: `LocalObjectStore`):

```
packages/<package_id>/
    manifest.json
    lesson-plan.json
    scenes/<order:03d>-<scene_id>.json
    assets/<sha256><ext>
```

* `<package_id>` is a UUID (V0) and equals `manifest.package_id`. It **MUST** be
  the only identity a consumer needs; the storage prefix is not part of the
  contract.
* `<scene_id>` **MUST** be flattened to a filename-safe component: every
  character outside `[A-Za-z0-9_-]` becomes `-`. A scene id that is an OOXML part
  path (`ppt/slides/slide1.xml`) therefore becomes `ppt-slides-slide1-xml`.
* `<order>` is the scene's `order`, zero-padded to three digits, so a directory
  listing is in lesson order.
* `<sha256>` **MUST** be the lowercase hex SHA-256 of the asset bytes. Assets are
  **content-addressed**, so two scenes that share a render contribute one file.

## 2. Manifest = envelope, commit point, reference list

`manifest.json` **MUST**:

* validate against `manifest.schema.json` (`additionalProperties: false`);
* list every package file — except itself — in `files[]`, with `path`, `sha256`
  and `media_type`;
* be written **last**, so a reader that cannot see the manifest sees no package
  at all. The manifest is therefore the transaction boundary of a package build;
* never list itself. Its own checksum is not part of the envelope.

`sha256` **MUST** be recomputed and compared on read. A mismatch is
`CHECKSUM_MISMATCH` and blocks publication (`DEC-CONTENT-004`).

`files[]` **MUST** be sorted by `path`, so a rebuild of unchanged content is
byte-identical.

### Manifest fields the builder fills from context

| Field | V0 baseline value | Why |
| --- | --- | --- |
| `schema_version` | `1.0.0` | `manifest.schema.json` `const` |
| `content_package_version` | `cpv-<16 hex>` | deterministic cache key: source checksum + compiler version + renderer `config_hash` |
| `lesson_plan_versions` | `["lp-<16 hex>"]` | same cache key; a content change is visible as a version change (`DEC-CONTENT-005`) |
| `knowledge_index_version` | `"unindexed"` | indexing is V0-014; `DEC-CONTENT-002` requires a usable package without it, so the sentinel is explicit rather than invented |
| `teaching_graph_version` | `null` | the baseline path is AI-free; `null` is the schema-valid "no Teaching Graph" value |
| `created_at` | RFC 3339 UTC | injectable, so a rebuild can be asserted byte-stable |

Review/publish state (`READY` / `REVIEW_REQUIRED`) is **not** a manifest field:
the schema forbids extra properties, and state belongs to the job/version rows
and to `PackageValidationReport`, not to an immutable content envelope.

## 3. Reference rules (what the schemas cannot express)

Every reference inside a package **MUST** be package-relative:

| Reference | Rule | Violation code |
| --- | --- | --- |
| `scene.fallback_asset` | absolute path of a file listed in `manifest.files[]` | `MISSING_ASSET`, `INVALID_REF` |
| `scene.steps[].object_ids[]` | a `source_id` of an object in the *same* scene | `INVALID_REF` |
| `lesson-plan.sections[].scene_id` | a `scene_id` present in the package | `INVALID_REF` |
| `lesson-plan.sections[].scene_step_id`, `safe_markers[]` | a `step_id` of the referenced scene | `INVALID_REF` |

A scene **MUST NOT** reference the compiler's internal asset store
(`renders/<sha>.svg`). That key is a compiler implementation detail; publishing it
would couple the runtime to the compiler's storage and break
`DEC-CONTENT-005` isolation.

## 4. Scenes and reveal steps

* A scene document is the CTF scene lifted from the Content IR with `steps`
  filled in and `fallback_asset` rewritten to the package path.
* **Baseline reveal semantics:** V0-004 extracts no animation or timing data, so
  the baseline builder emits exactly **one** step per scene, `kind`
  `ALL_VISIBLE`, listing every object id in the extractor's `reading_order`.
  Objects are never dropped or reordered. (Multi-step reveals require animation
  extraction and are not part of V0-004/V0-006.)
* `fidelity` is carried from the render stage (`DEC-CONTENT-006`); only the
  schema's values may appear. `STRUCTURAL_RENDERED` reproduces the source slide's
  own styling (faithful mode); `THEMED_RENDERED` re-lays the content out as one
  readable column in the platform theme (default mode, V0-019) and so is not ranked
  against the source-fidelity values; `DEGRADED_RENDERED` requires a human check of meaning.
  A failed render is a `FAILED` *status*, not a fidelity, and blocks packaging
  instead of entering one.

## 5. Lesson plan and safe markers

The baseline lesson plan is a **fallback order derived from the deck**: one
section per scene, in scene order.

* `section_id` = `<lesson_id>#section-<index>`.
* `type` is `EXPLANATION` when the scene contains any non-empty text paragraph,
  otherwise `MEDIA`. The baseline invents no pedagogy: `EXAMPLE`, `QUIZ` and
  `DISCUSSION` come from AI enrichment and teacher review (out of V0 scope).
* `script` is the scene's speaker notes, verbatim (or `null`). `DEC-CONTENT-008`
  makes notes weighted evidence, so they are never paraphrased or dropped.
* `scene_step_id` is the scene's first step — the point where the section enters
  its scene.
* `safe_markers` lists **every** `step_id` of the scene, in the format
  `<scene_id>#step-<n>`. These are the only points at which the runtime may
  pause or resume without leaving the presentation in a half-revealed state, so
  the marker vocabulary is fixed by the baseline: a marker that is not a step of
  the referenced scene is `INVALID_REF`.
* `fallback_script` is `null` in the baseline; it is filled when a lesson has a
  reviewed script that needs a degraded-path variant.

## 6. What a package must never contain

* A source document (`.pptx`, `.ppt`, `.pptm`, `.ppsx`, `.odp`, `.pdf`) — the
  runtime never parses originals (`DEC-CONTENT-001`).
* Any form of ZIP/OOXML container or raw source markup (`<p:sld…`).
* A dependency on an OOXML/XML parser in the builder or in the packaged files.

`SOURCE_DOCUMENT_PRESENT` blocks publication.

## 7. Validation codes

`validate_package()` reports these issue codes. All are errors except the
`REVIEW` ones.

| Code | Meaning |
| --- | --- |
| `INVALID_MANIFEST` | the manifest is not an object |
| `MISSING_MANIFEST_FIELD` / `UNKNOWN_MANIFEST_FIELD` | schema `required` / `additionalProperties: false` |
| `INVALID_MANIFEST_FIELD_TYPE`, `INVALID_MANIFEST_SCHEMA_VERSION` | field shape/const |
| `MISSING_KNOWLEDGE_INDEX_VERSION`, `INVALID_LESSON_PLAN_VERSIONS`, `INVALID_TEACHING_GRAPH_VERSION` | envelope field rules |
| `INVALID_FILES`, `INVALID_FILE_ENTRY`, `INVALID_CHECKSUM_FORMAT` | `files[]` entries |
| `MANIFEST_SELF_REFERENCE`, `DUPLICATE_FILE_PATH`, `ORPHAN_FILE` | reference-list integrity |
| `MISSING_FILE_BYTES`, `CHECKSUM_MISMATCH` | a listed file is absent or mutated |
| `SOURCE_DOCUMENT_PRESENT` | a source document leaked into the package |
| `MISSING_DOCUMENT`, `INVALID_JSON` | an unreadable scene/lesson-plan document |
| `MISSING_SCENE_FIELD`, `INVALID_SCENE_ID`, `DUPLICATE_SCENE_ID`, `SCENE_DIMENSIONS`, `INVALID_SCENE_STEPS`, `INVALID_SCENE_STEP`, `INVALID_FIDELITY`, `MISSING_FALLBACK_ASSET` | scene shape |
| `MISSING_LESSON_PLAN_FIELD`, `EMPTY_LESSON_PLAN`, `INVALID_LESSON_SECTION`, `INVALID_SECTION_TYPE`, `INVALID_SAFE_MARKERS`, `LESSON_PLAN_VERSION_MISMATCH` | lesson-plan shape |
| `INVALID_REF`, `MISSING_ASSET`, `NO_SCENES` | cross-document references |
| `DEGRADED_REQUIRES_REVIEW`, `RENDER_REQUIRES_REVIEW` | **review** severity |
| `RENDER_NOT_PUBLISHABLE` | V0-005 fidelity gate failed |

## 8. Determinism and idempotence

Given the same source bytes, compiler version and renderer `config_hash`, a build
**MUST** produce byte-identical `manifest.json` and byte-identical file digests
(asserted in `backend/tests/test_package_builder.py`). Rebuilding overwrites
identical bytes, so the operation is idempotent and safe to retry.

## 9. Not in this contract

* Provider/renderer technology: `DEC-TECH-005` is `OPEN` (FND-002).
* Job claiming, leases, checkpoints, retry persistence: V0-003.
* Publication lifecycle and the Teaching Graph: V0-008+ / V0-012.
* Knowledge indexing: V0-014 (`knowledge_index_version` stays `"unindexed"`).
