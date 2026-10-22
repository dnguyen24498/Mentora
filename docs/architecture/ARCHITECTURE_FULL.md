# Mentora Canonical Architecture Full

Generated from canonical numbered files.

<!-- SOURCE: 00_ARCHITECTURE_BASELINE.md -->

# Architecture Baseline

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Declare the canonical stable architecture agreed across the design discussion.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Stable core

```text
Source Materials -> Secure Import Gateway -> Deterministic Content Compiler
-> Content IR -> Baseline Content Package
-> Selective AI Enrichment + RAG Indexing
-> Validation/Human Review -> Published CTF Package
-> Runtime Session Plan -> Classroom Actor
-> Lesson / Turn / Timeline / Question / Checkpoint modules
-> Teacher Orchestrator and replaceable Capability Services
-> WebSocket presentation + WebRTC SFU -> React Classroom
```

## Baseline promise

Mentora promises approved-content teaching, deterministic classroom control, grounded answers, controlled student speech, version consistency, recoverable failure, and measurable realtime behavior. It does not promise perfect arbitrary-document understanding, absolute zero failure, or autonomous replacement of lecturers.

## Planes

Compiler, Publication, Runtime Control, Capability, Media, Presentation, Data, and Governance planes. Their logical boundaries are stable even if V1 deployment groups modules.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-003`
- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
- `DEC-CONTENT-008`
- `DEC-CONTENT-009`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`
- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`
- `DEC-RUNTIME-007`
- `DEC-TURN-001`
- `DEC-TURN-002`
- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-TURN-008`
- `DEC-TURN-009`
- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-003`
- `DEC-DATA-004`
- `DEC-DATA-005`
- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
- `DEC-DEPLOY-001`
- `DEC-DEPLOY-002`
- `DEC-PERSONAL-001`
- `DEC-SCORM-001`


<!-- SOURCE: 01_OVERALL_ARCHITECTURE.md -->

# Overall Architecture

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Show end-to-end components and flows.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Overall diagram

```text
Institution: IdP/SSO | LMS/SIS | Teachers | Students | IT
                              |
                    Edge / API / WebSocket
                 +------------+------------+
                 |                         |
Content & Publication                 Runtime Control
Teacher Studio                        Ordered commands by class_id
Secure Import                         Classroom Actor
Compiler/IR/Renderer/Media            Lesson/Turn/Timeline/Checkpoint
Baseline + AI Enrichment              Teacher Orchestrator
Review -> Published CTF               Snapshot/Event Recovery
                 |                         |
                 +------------+------------+
                              |
Capability: Knowledge/RAG | LLM | STT | Voice/TTS | Vision/OCR
Presentation: scene/step/quiz/caption events
Media: SFU/TURN, shared teacher track, granted student track
Data: durable DB, event log, Redis, search, object storage
Governance: identity, policy, consent, audit, retention, SLO
```

## Content flow

Source -> deterministic extract/render/media -> baseline -> optional semantic enrichment -> review -> immutable package/index.

## Classroom flow

Start -> pin versions/region -> initialize actor/media -> teach -> question -> grounded answer -> checkpoint resume -> complete.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`


<!-- SOURCE: 02_ARCHITECTURAL_INVARIANTS.md -->

# Architectural Invariants

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define conditions that must remain true under success, retry, and failure.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Content invariants

Runtime never parses source. Published package immutable. Active version tuple immutable. Baseline usable without Teaching Graph. Retrieval cannot cross scope/version.

## Classroom invariants

Exactly one logical owner; at most one floor; STT implies floor; student SPEAKING excludes teacher PLAYING; stale epoch cannot mutate/authorize; duplicate command creates one logical effect.

## Recovery invariants

Snapshot/checksum/schema validated before replay. Recovery never silently upgrades artifacts. All reservations/tokens have terminal release/revoke paths.

## Security invariants

Every resource is tenant-scoped; provider credentials never reach clients; audio transmission is visible and authorized; raw student audio retention is disabled by default.

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-DATA-004`
- `DEC-DATA-005`


<!-- SOURCE: 03_DOMAIN_OWNERSHIP_AND_VERSIONING.md -->

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


<!-- SOURCE: 04_CONTENT_COMPILER.md -->

# Content Compiler Architecture

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify secure deterministic compilation and selective enrichment.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Pipeline

Validate/scan/store -> structural extraction -> rendering router -> media processing -> reveal semantics -> Content IR -> baseline builder -> selective AI enrichment -> validation.

## Rendering

Record engine/version/fonts/warnings/provenance and classify native-compatible-structural-degraded-failed. Failed blocks publication; degraded meaning requires review. A component the renderer draws in the platform look, and a source font it had to substitute, are **warnings** on a structural scene: they are disclosed and countable, not escalated to a human, because nothing is missing from the output.

Two local render modes sit behind the renderer interface while the production renderer technology is `OPEN`:

- **`faithful` (default)** reproduces the **source slide's own layout and styling** and reports `STRUCTURAL_RENDERED`: the effective theme colours and font scheme, slide/layout/master backgrounds and placeholder inheritance, the art it inherits from its layout and master (below), shape fills/lines/gradients/geometry/rotation, exact run and paragraph formatting, embedded pictures with crop, tables, and connectors. A component it cannot reproduce is **drawn in the platform look, in place**, rather than dropped or degraded: an **unavailable source font** is substituted with the platform's type stack (deterministically — the client's own fonts can never change the asset) and recorded as `FONT_SUBSTITUTED:<family>`, and a frame whose typeface was substituted is shrunk to stay inside the author's frame instead of spilling over its neighbour; a **chart / SmartArt / WordArt / equation / graphic frame** becomes a flat platform panel labelled with the object (`UNSUPPORTED_OBJECT:<kind>`); a **picture that cannot be inlined** (EMF/WMF/TIFF, over budget, bytes withheld) becomes a flat platform panel labelled with the part. Each is a *warning* on a `STRUCTURAL_RENDERED` scene, not a review blocker — the deck's content is complete and its layout is the author's, so meaning is not at risk. Slide-level `DEGRADED_RENDERED` remains reserved for a scene that genuinely cannot be drawn.
- **`themed`** (opt-in) **re-lays the content out**: *the grouping is the author's, the content is the author's, the look is the platform's*. The extracted objects are queued with their source boxes and a binary widest-gap XY-cut (`flow.structure`) recovers the slide's **rows and columns** — a cell keeps the objects the author grouped together, so an icon stays beside its label and a card keeps its parts. Each recovered cell is then folded into flow blocks (a list of paragraphs, a table, a row of pictures) and re-laid out by a single measuring pass over a cursor — position and measurement are the same computation, so two blocks cannot overlap by construction — behind a hoisted heading (kicker/title/subtitle over one hairline rule), with the page number in a reserved bottom strip the flow may not enter. A cell that draws more than one block becomes a **card**: the content is inset and a flat platform surface panel is painted behind it (no border). The look is the platform's throughout: its type stack, its type scale, its palette; no source typeface, colour, fill or geometry is reproduced. Its fidelity is `THEMED_RENDERED` — a re-layout, **not** a rank on the fidelity-to-source ladder — and the gate is *content completeness*, not visual fidelity: nothing is re-selected, re-ordered or dropped. The source's own sizes select one of three theme rows (`lead`/`body`/`caption`), so a 40 pt statistic still reads as a statement beside a 12 pt note, and its bold/italic runs survive. Content that cannot be fitted even at the smallest readable type scale (`flow.LADDER`, then a continuous shrink to `theme.min_scale`) is still drawn, flagged `TEXT_OVERFLOW:<scene>`, degraded for review, and the page number is omitted so nothing is covered. Text metrics are estimated from a font-free advance table (`textmetrics.py`), so a line may break a word early — it can never collide with its neighbour.

A component the default renderer cannot reproduce is never silently flattened: it is drawn in the platform look and named in a warning. The renderer never reads the source package: it receives the Content IR and the picture bytes the compiler injects (`DEC-CONTENT-001`). Both modes estimate text metrics rather than measuring them, so a substituted typeface can wrap a line a word earlier than PowerPoint would.

A **`picture` slide background** is the one part of the look whose relationship belongs to a *different* part than the slide: decks put their art-directed dark backgrounds on the title/section **layouts**, and a layout's `p:bg` references the layout's own rels. Extraction therefore resolves each level of the cascade against the part that declares it (slide, then layout, then master); if the picture's bytes cannot be inlined the level does not mask a usable background further up — it warns and the next background up is used. Getting this wrong is invisible in a white deck and ruinous in a dark one: the background image is lost, and the deck's light text becomes unreadable on the fallback white.

A slide is not only the shapes stored on it: a deck keeps its shared **chrome** — the crest, the faculty badge, a rule, a static label — on the **layout** (or the master), and PowerPoint paints it *under* the slide's own objects. Extraction therefore also walks the master's and the layout's shape trees for **non-placeholder** art (`inherited_objects`, each part walked with its own identity so a layout's picture resolves against the layout's rels — the same rule as the background cascade), honouring `showMasterSp` on the slide (hides the whole inherited layer) and on the layout (hides the master's shapes only), and the renderer paints it master-first, layout-second, the slide's own objects last. A layout/master **placeholder** is deliberately not inherited: it is a definition the slide's own placeholder replaces, and the empty ones are not rendered. Inherited art is *not* slide content — it carries no reading order of its own and never joins the slide's text or object count (`objects`) — but it is what makes a deck's slides look like the deck: without it the reference deck's 26 slides lose the top-right logo pair they carry only in the layout. The opt-in `themed` mode re-authors the look, so it does not carry the deck's chrome, and says so in its notice.

## Vision

Invoked only for scans, diagrams, complex charts, SmartArt fallback, or meaning carried by position/color/arrows. Every invocation records reason, model/prompt versions, source refs, confidence, and review state.

## Security/reproducibility

Sandbox untrusted files, never execute macros/scripts/OLE, bound resources and archive expansion. Deterministic cache key uses source checksum, compiler version, renderer identity, and config hash.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-006`
- `DEC-CONTENT-009`


<!-- SOURCE: 05_CONTENT_MODELS_AND_FIDELITY.md -->

# Content Models, Fidelity, and Media

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define scenes, stable objects, reveal steps, and multimodal timelines.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Scene includes stable ID/source, normalized dimensions/bounds, fallback render, structured objects, notes, refs, fidelity, warnings, provenance, and steps. Stable object identity changes referenced by lessons require review. A scene also carries the art it **inherits** from its layout and master (`inherited_objects`, V0-019 v7): the deck's shared chrome, painted beneath its own objects and outside its reading order, text and object count.

## Fidelity classification

`fidelity` records **how** a scene's fallback render relates to its source, and every scene carries exactly one value:

| Value | Meaning |
| --- | --- |
| `NATIVE_RENDERED` | produced by a native/compatible engine (no such engine is accepted yet) |
| `COMPATIBLE_RENDERED` | produced by a compatible engine (no such engine is accepted yet) |
| `STRUCTURAL_RENDERED` | the source slide's own layout and styling reproduced structurally — the **default** (V0-019 v5); a component that cannot be reproduced is drawn in the platform look in place and warned about |
| `THEMED_RENDERED` | the content re-laid out in the platform theme (the author's grouping kept, the look re-authored) — opt-in |
| `DEGRADED_RENDERED` | renderable, but a human check of meaning is required |

`THEMED_RENDERED` is deliberately **not** on the fidelity-to-source ladder: nothing is claimed about the original appearance, so consumers must not read it as "better" or "worse" than `STRUCTURAL_RENDERED`. It is still an explicit, non-native classification, never a native render. Its content-completeness alarm is `TEXT_OVERFLOW:<scene>`: the scene's content does not fit the page even at the smallest readable type scale. The content is still drawn in full (never truncated) and the scene is degraded for review; the platform omits its own page number on such a scene so nothing is painted over the spill.

`STRUCTURAL_RENDERED` is the default because it reproduces the author's own slide. Its incompleteness alarms are component-scoped and are **warnings, not degradations**: `FONT_SUBSTITUTED:<family>` (the run is drawn in the platform's type stack, in its original frame), `UNSUPPORTED_OBJECT:<kind>` (a chart/SmartArt is drawn as a platform panel, in place), `UNSUPPORTED_MEDIA:`/`MEDIA_BUDGET_EXCEEDED:`/`MEDIA_UNAVAILABLE:` (a picture that cannot be inlined is drawn as a platform panel, in place). The scene is still publishable without a human accepting a "degradation" that is not visible in the output; `DEGRADED_RENDERED` stays reserved for a scene that genuinely cannot be drawn.

Instructional animations become visibility/semantic steps; decorative effects may be dropped. Video becomes timestamped ASR, scene-change frames, OCR, visual events, and segments that runtime can play/pause/resume exactly.

## Locked Decisions Implemented

- `DEC-CONTENT-006`
- `DEC-CONTENT-007`


<!-- SOURCE: 06_CTF_TEACHING_GRAPH_AND_LESSON.md -->

# CTF, Teaching Graph, and Lesson

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Separate package, semantics, instructional sequence, and runtime plan.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Content Package owns showable content. Teaching Graph owns reviewed concepts/prerequisites/misconceptions/objectives/evidence. Lesson Plan owns approved sequence, scene/step refs, safe markers, activities, scripts, durations, and fallbacks. CTF references these immutable components and their checksums.

Baseline lesson can operate without Teaching Graph. Speaker notes follow evidence authority and conflict workflow.

## Locked Decisions Implemented

- `DEC-CONTENT-002`
- `DEC-CONTENT-003`
- `DEC-CONTENT-004`
- `DEC-CONTENT-008`


<!-- SOURCE: 07_PUBLICATION_AND_REVIEW.md -->

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


<!-- SOURCE: 08_RUNTIME_CONTROL_PLANE.md -->

# Runtime Control Plane

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define command path, modules, and deployment boundary.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Gateway authenticates, validates schema, authorizes, then places commands in an ordered per-class mechanism. Classroom Actor deduplicates and validates epoch/version/invariants, transitions state, persists event/outbox, and invokes idempotent capabilities.

Actor contains session, lesson, turn, timeline, question, checkpoint coordination. Teacher Orchestrator is called for pedagogical decisions but cannot mutate authoritative state directly. V1 deploys control modules together.

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-RUNTIME-003`
- `DEC-DATA-003`
- `DEC-DEPLOY-001`


<!-- SOURCE: 09_CLASSROOM_ACTOR_AND_RECOVERY.md -->

# Classroom Actor and Recovery

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify ownership, fencing, snapshots, replay, and reconnect.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Commands for a class are serialized by `class_id`. Ownership acquisition increments actor epoch. State version increments per accepted transition. Downstream tokens/effects carry epoch and deterministic IDs.

Snapshot contains all orthogonal state regions, versions, lesson/scene/step, queue/floor, timeline checkpoint, pending effects, epoch/version/sequence, schema version, and checksum. Recovery restores, replays, reconciles, revokes stale floor, and resyncs clients using snapshot plus deltas.

## Implemented aggregate

The Classroom Actor's deterministic core is implemented in `backend/app/classroom/aggregate.py` (`ClassroomAggregate`, `Command`, `Event`, `CommandResult`), driven by the service's command entry points (`ClassroomService.navigate_scene` / `record_checkpoint` / `end_class`) and persisted by `ClassRepository.commit_transition`. It is an **in-process** reducer — one aggregate instance per class, cached by the service with a per-class lock (`DEC-RUNTIME-001`), and the durable store stays the truth: every accepted transition appends a validated snapshot and updates the session counters in one transaction, guarded by a `WHERE state = ? AND state_version = ? AND actor_epoch = ?` clause, so a writer that lost a race reloads and re-handles instead of clobbering (`DEC-RUNTIME-007`). The commands are `START`, `NAVIGATE_SCENE`, `CHECKPOINT`, `END` and `REOPEN`; each accepted command emits one event (`classroom.session.started`, `classroom.scene.changed`, `classroom.checkpoint.recorded`, `classroom.session.ended`, `classroom.session.reopened`) and increments `state_version` and `event_sequence` together. Handling runs in the state machine's order: **command-id dedup first** (a replayed command returns its stored terminal verdict and writes nothing — `DEC-RUNTIME-003`), then epoch fencing, then state-version fencing, then the transition, then the post-transition invariant check (a non-active state has no valid floor or queued turn; an STT reservation implies a floor; at most one floor). `START` is the aggregate's own first command: `start_class` builds the session, runs `START`, and commits the snapshot the aggregate produced, so *all* classroom mutations pass through the one reducer. `END` transitions `ACTIVE/DEGRADED -> COMPLETED` (`ENDING` is in-process only, never persisted), records the final checkpoint and revokes the session's live join credentials, so a class end leaks no token. `REOPEN` transitions `COMPLETED -> ACTIVE` for the same class occurrence: it keeps the pinned tuple and roster, returns the lesson to its first position, and bumps `actor_epoch` before emitting `classroom.session.reopened`, so join credentials and fenced commands from before the end are stale (`DEC-RUNTIME-007`). While a class is `COMPLETED`, participant reads of the snapshot and pinned scenes are refused (`CLASS_ENDED`); staff review reads by capability. `restore` validates schema version and checksum before use, so a corrupted snapshot is refused rather than replayed (`DEC-DATA-004`); a restart therefore restores the pinned tuple and the scene position from the newest snapshot, and the next command continues from that version. Idempotency memory is in-process — durable cross-restart dedup and the ordered per-class event log/outbox are `DEC-DATA-003`'s open technology and V1-002's ("actor epoch event outbox and replay"), so `DEC-TECH-001`/`DEC-TECH-002` remain `OPEN` and no broker or actor framework is assumed. Tests: `backend/tests/classroom/test_aggregate.py` (the reducer: start, invalid transition, duplicate command, stale epoch/version fencing, snapshot round trip, corrupted snapshot) and `backend/tests/classroom/test_classroom_commands.py` (navigation/checkpoint/end persisting through the aggregate, restart restoring pinned tuple and scene position, a duplicate command writing one snapshot, and a stale command writing nothing).

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`
- `DEC-RUNTIME-007`
- `DEC-DATA-003`
- `DEC-DATA-004`


<!-- SOURCE: 10_TEACHER_ORCHESTRATOR.md -->

# Teacher Orchestrator

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Separate pedagogy from deterministic control.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Teacher Orchestrator decides explanation strategy, next approved instructional action, retrieval need, evidence use, quiz/check, adaptation, answer plan, and natural resume phrase. It receives pinned session context and returns schema-valid proposals.

Classroom Actor validates proposal against policy, current state/version, lesson plan, and permissions. Orchestrator does not own floor, lesson truth, attendance, grades, artifacts, or media transport.

## Locked Decisions Implemented

- `DEC-RUNTIME-002`
- `DEC-PERSONAL-001`


<!-- SOURCE: 11_RAISE_HAND_AND_TURN_CONTROL.md -->

# Raise Hand and Turn Control

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define control-first, audio-on-demand interaction.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Group microphones remain unpublished. Raise Hand is a control command. Queue uses configurable fairness. Before floor: reserve STT, verify connection, reach safe marker, checkpoint, cancel teacher audio, await ACK or safe timeout, mint fenced short-lived floor token.

On publication ACK, enter SPEAKING and start STT. Finish/VAD/timeout/revoke/disconnect transitions exactly once to finalization; stop STT, unpublish, revoke, release capacity, produce final transcript. Typed question remains available.

## Locked Decisions Implemented

- `DEC-TURN-001`
- `DEC-TURN-002`
- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-TURN-008`
- `DEC-TURN-009`


<!-- SOURCE: 12_TIMELINE_PRESENTATION_AND_RESUME.md -->

# Timeline, Presentation, and Resume

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Coordinate speech, visuals, cancellation, and semantic continuation.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Use marker priority: native TTS marker, forced alignment, audio PTS, estimated offset, segment fallback. Presentation events include deadline policy and target version. Client ignores duplicate/stale generations/events and reports sequence gaps.

Audio cancellation names cancel-through generation; client stops/clears/discards/ACKs. Checkpoint precedes student invitation. Resume validates versions/checkpoint, restores presentation, generates bridge phrase, and starts new segment/generation.

## Locked Decisions Implemented

- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`
- `DEC-TURN-007`

## Implemented narration (V0-013)

The presentation pipeline narrates each pinned slide: pinned script → word-safe
chunks → provider-neutral voice → one WAV per chunk, played in order as it arrives,
and the slide advances when its narration has been heard. Speech failure shows the
authored text and paces the slide by its length (`DEC-TURN-009`). A slide change,
pause or end aborts the stream and cancels synthesis; resuming restarts the current
slide as a new generation. The teacher-scoped
`GET /classes/{classId}/narration/{order}` stream remains available as a manual
preview, but it is no longer the normal producer: since V0-028 the class server's
background presenter reads the same timeline.

An enrolled student's page attaches to the current **live generation** through an
in-process relay (`GET /classes/{classId}/narration`): it starts no synthesis and
copies the same WAV chunks, so a class does not pay one provider call per learner.
The relay is a V1-005 bridge, not the media plane — it is single-process and
best-effort, returns `204` while there is no current generation (the page retries),
ends at each generation's terminal verdict, and sends attached listeners a
cancellation when the presenter pauses or moves. The current slide is the unit of
replay: a late joiner receives the buffered chunks from that slide's start, so the
fast local mock — which can synthesize a whole slide before the student's next
attach — does not leave the class in silence, and the next slide supersedes it. A
completed generation stays replayable for a short TTL; the page passes
`after_generation` so waiting for the next slide does not replay the one it just
heard, and `expected_scene_id` keeps the audio under the slide the authoritative
snapshot shows. A student joining mid-slide is therefore aligned with the displayed
slide but may be a few seconds behind the presenter's own playout.
`DEC-TECH-004` remains `OPEN`; a multi-worker deployment needs the ordered/shared
path that decision will choose, not this in-memory relay. Students see the slide
with no transcript by default (a collapsed accessibility disclosure keeps the text
available) and can enable sound if the browser blocks autoplay.

## Background presentation (V0-028)

A started class is presented by the **API process**, not by the teacher's browser
tab. `backend/app/classroom/timeline/presenter.py` holds one runner per
`(institution, class)`:

- `POST /classes/{id}/start` and `POST /classes/{id}/reopen` schedule the runner
  after the response, so it can never race the transaction that wrote the start or
  reopen snapshot.
- The runner reads only the session's **pinned** package (`DEC-CONTENT-005`),
  synthesizes the current scene through the same `TimelineService` and publishes it
  into the class relay, then waits for its playout. It advances the class through
  the aggregate's normal `NAVIGATE_SCENE` command, fenced by
  `expected_state_version` (`DEC-RUNTIME-007`); it never writes state directly.
- Playout waits `max(first_audio_at + total_audio_ms, last_audio_at) + grace` for a
  completed generation. An empty script, a speech fallback or a failed provider
  uses a text dwell of 5–30 s at 160 wpm so the lesson keeps moving instead of
  stopping in silence.
- A teacher's pause is class-level: it cancels any **in-flight** provider
  generation (listeners receive the relay's cancellation for it) and freezes the
  position. Resume starts the current scene from its beginning — a semantic
  segment, never a byte offset (`DEC-RUNTIME-005`). The HTTP relay may already have
  delivered a fully synthesized slide to a browser, so audio already buffered there
  can still drain; retroactively pausing a media stream is the SFU's job
  (`DEC-TECH-004`/V1-005), not this bridge's.
- A manual `POST /classes/{id}/navigate` is observed by the runner, which aborts the
  old generation and starts the newly authoritative scene. A completed generation
  that is still current remains replayable to a late listener.
- At the last pinned slide the runner **holds** (`at_end`) rather than ending the
  class or looping. Ending (`POST /classes/{id}/end`) stops it synchronously, so
  no further scene is presented; reopening starts a fresh runner at the first slide
  of the new epoch.
- `GET /classes/{id}/presentation`, `POST .../presentation/pause` and
  `POST .../presentation/resume` are the teacher's `class:write` control/status
  surface. `resume` also recovers an `ACTIVE` class after an API restart: the
  runner is in-process and not durable, so the teacher's page offers **Start
  presentation** when `running` is false.

This is explicitly a **development bridge**. `DEC-TECH-003` (durable
workflow/scheduler) is `OPEN`, so the runner is single-process and lost on restart;
`DEC-TECH-004`/V1-005 mean audio still travels over the HTTP relay, not the SFU.
`MENTORA_BACKGROUND_PRESENTATION=0` disables it and the presentation routes report
`available: false`. The teacher's page follows the authoritative snapshot by a
quiet ~1.5 s poll and plays the relay without starting a second synthesis (V0-028).
The client-local V0-026 autoplay pacing is no longer used.


<!-- SOURCE: 13_MEDIA_SPEECH_AND_VOICE.md -->

# Media, Speech, and Voice

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define SFU topology, STT/TTS lifecycles, floor media, and voice governance.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

One class has one SFU room and shared teacher audio publisher. Students subscribe; floor holder temporarily publishes one audio track. TURN and quality telemetry support difficult networks.

STT has reservation/start/partial/final/cancel/release; partial is ephemeral. TTS has capacity reservation, marker plan, streaming, generation cancellation, and fallback. Authorized cloned voice records consent/scope/expiry/revocation/deletion/audit; neutral voice is fallback.

On media node failure stop grants, revoke floor, reconnect, republish, restore snapshot, and resume at segment boundary.

## Implemented TTS provider

The teacher voice capability's provider-neutral core is implemented as a **domain port plus a replaceable adapter** (V0-012): `backend/app/speech/` is the domain — the `SpeechProvider` interface (`port.py`), the models (`models.py`), the `SpeechService` that reserves, synthesizes, cancels, releases and falls back (`service.py`), the classified errors (`errors.py`) and structured telemetry (`telemetry.py`) — and `backend/app/providers/deterministic.py` is the one adapter V0 runs with. The adapter is **deterministic** (the audio for a piece of text is a pure function of voice/language/text — sha256-seeded PCM frames) and **dependency-free** (no network, credentials or GPU), so it doubles as the deterministic mock and as the dev-stack mock (`dev/mocks/tts_mock.py`).

The provider technology is **not decided**: `DEC-TECH-007` (TTS/OmniVoice deployment and GPU capacity) is `OPEN`, so `ADR-P007` applies — *"until accepted, provider-neutral interfaces and mocks are used"* — and the adapter is reported as `neutral-deterministic@1.0.0`, never as a vendor provider. The domain imports nothing outside itself and the stdlib (`tests/speech/test_layering.py` asserts the boundary), so no provider SDK or vendor error can reach the classroom domain.

Every documented behaviour is honoured in one place (the port base), so no adapter can skip it: a **generation** is the idempotency key (a replayed synthesis returns its stored terminal verdict; a replayed cancel returns its stored ACK — `DEC-RUNTIME-003`); **capacity is reserved before use** and released on every terminal path (admission control, `DEC-RELIABILITY-001`); the end-to-end **deadline** (an injected clock) turns an overrun into `SYNTHESIS_TIMEOUT` rather than an indefinite wait; **cancellation** is cooperative and idempotent; **retry** is bounded, classification-driven, and only before any audio has left an attempt (a partially emitted stream is never duplicated); and a **circuit breaker** opens after a configured number of consecutive failures and refuses further admission. **Markers are semantic** (`DEC-RUNTIME-006`): a marker plan indexes into the normalized text and the millisecond realization is derived output. Failure **routes neutral voice, then text**: a refused voice re-routes to the neutral voice, and a timeout/provider error returns the utterance as text with its semantic markers preserved, so the lesson always continues (`DEC-TURN-009`).

## Locked Decisions Implemented

- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-008`
- `DEC-DEPLOY-002`
- `DEC-RELIABILITY-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-006`


<!-- SOURCE: 14_LLM_RAG_AND_AI_SAFETY.md -->

# LLM, RAG, and AI Safety

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define grounded generation and guardrails.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Knowledge Service applies authorization and pinned version filters before hybrid retrieval, returns evidence IDs/source/index version, and rejects incompatible results. LLM Router selects allowed model by task, latency, cost, residency, and capability.

LLM output is explanatory text or schema-valid proposal. Application re-authorizes tool actions. Prefer approved evidence, label supplement/uncertainty, never fabricate citations, and escalate high-impact/safety issues.

## Locked Decisions Implemented

- `DEC-DATA-005`
- `DEC-RELIABILITY-001`
- `DEC-RUNTIME-002`


<!-- SOURCE: 15_FRONTEND_CLASSROOM_AND_STUDIO.md -->

# Frontend Classroom and Teacher Studio

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define authoritative client state, UX, reconnect, and review interfaces.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Separate snapshot/event reducer, media state, ephemeral UI, device permissions, and accessibility preferences. Apply contiguous events for current epoch; duplicates/stale ignored; gaps require resync.

Classroom displays content, captions, transcript, teacher state, queue, floor countdown, mic indicator, Finish, quiz, and recovery. Teacher Studio reviews fidelity, notes, reveals, semantics, citations, lessons, policy, voice, and publication diff.

## Implemented classroom client

The classroom client is implemented in `frontend/src/classroom/`. It is a **projection**, never a source of truth: the Classroom Actor owns authoritative state, and the client holds a derived view rebuilt from the authoritative snapshot (`GET /classes/{id}/snapshot`, the durable `runtime-snapshot@1` document) plus contiguous ordered events. The state is split into separate slices (`frontend/src/classroom/state/`): the **event reducer** (`reducer.ts` — the only slice derived from the actor's stream), the raw **snapshot**, **media** state and **ephemeral UI / accessibility preferences** in `store.ts`. The reducer is pure: it applies an event only when it is **contiguous for the current epoch** (`sequence === lastSequence + 1`), **ignores duplicates and stale events** (`sequence <= lastSequence` — `DEC-RUNTIME-003`), **discards an effect from a superseded epoch** (`DEC-RUNTIME-007`), and reports a **sequence gap** rather than applying out of order. A gap, a stale epoch or a failed load freezes the client (`status !== 'live'`), disables the command controls and requests a resync; the session (`session.ts`) answers a resync by re-reading the authoritative snapshot with bounded retry (`DEC-RELIABILITY-001`) and resetting the event cursor — it never guesses at the missing events. A refresh is a fresh mount, so it restores scene and state from the snapshot (`DEC-RUNTIME-004`, `DEC-DATA-004`). The transport is an interface with one V0 implementation (`transport.ts`) that reads the snapshot only: the ordered per-class event mechanism is `DEC-DATA-003` and its technology is `OPEN`, so the shell reports `liveEvents:false`/`commands:false` and says so instead of faking a stream (that live path is V1-002). Group student audio stays inactive (`DEC-TURN-001`). The client emits structured telemetry — identities, counts and outcomes only, never scene text, transcript or audio (`telemetry.ts`).

## Background presentation in the client (V0-028)

The **class server** is now the presentation clock
(`backend/app/classroom/timeline/presenter.py`); the teacher's browser is a
follower and control surface. This is a deliberate correction: with the V0-026
client-local clock, closing the teacher's tab stopped the slides for every student.

- `ClassroomPage.tsx` starts a quiet `poll()` of the authoritative snapshot (about
  every 1.5 s) for a teacher. It is not a resync: no `resyncing` flicker and no
  disconnect on one transient failure, because the last authoritative scene stays
  on screen. The ordered stream is still `DEC-DATA-003` (`OPEN`, V1-002).
- `TeacherStage.tsx` keeps the pinned slide, Previous/Next and picker (each an
  ordinary fenced `NAVIGATE_SCENE`), shows the server's presentation status, and
  offers Pause/Resume, **Start presentation** when no runner exists (an API
  restart), and End/Reopen. A manual move is noticed by the runner, which restarts
  its narration at the chosen scene.
- The stage's voice is the presenter's relay (`mode: 'relay'`); it starts no second
  synthesis. It says whether the provider is the deterministic mock or the opt-in
  OmniVoice prototype, and offers **Enable sound** if the browser blocked autoplay.
  A relayed text fallback is shown as the slide's script (`DEC-TURN-009`).
- The `ClassroomHomePage.tsx` Start/Reopen actions now call the API and refresh the
  class list instead of navigating to `/classroom/{id}?autoplay=1`. The classroom
  no longer needs to stay open, and that URL flag is ignored. The client-local
  `playbackTiming.ts` pacing was removed with the tab clock.
- This remains a **development bridge**: the runner is in-process and lost on an
  API restart (`DEC-TECH-003` `OPEN`), and audio is HTTP relay, not the SFU
  (`DEC-TECH-004` `OPEN`, V1-005). The page says both rather than implying a
  durable scheduler or a media plane.

## Implemented pages and navigation

The app has four routed pages (`frontend/src/router.tsx`, dependency-free): the
material library (`/`), the Teacher Studio (`/studio/{artifactId}`), the
classroom (`/classroom/{classId}`) and the learning page (`/learn/{artifactId}`),
plus two **sectioned areas**: the Admin area (`/admin/{section}` —
overview, courses, classes, publications) and Settings (`/settings/{section}` —
general, rendering, teaching, accessibility). V0-021 adds three: **sign in**
(`/login`), a class's **student join page** (`/join/{classId}`) and the student's
**own fullscreen view** of a class (`/student/{classId}`). A shared navigation
(`frontend/src/components/SiteNav.tsx`) is embedded in every page header, so each
page is reachable from every other. The deck/class-scoped entries use the id the
page holds or the last one opened — remembered in `localStorage` alongside the
tenant — and are disabled with an explanation before an id exists. The library is
the hub: it lists the tenant's classes (`GET /classes`) and links each to its
classroom, and offers both the Studio and the learning page for a selected deck.

## Implemented identities and the student surface (V0-021)

`frontend/src/auth/` holds the identity half. `session.ts` is the signed-in
session (`localStorage`, shared across tabs like the tenant): the raw token for
the API client, the principal, the capability that issued it, and a memoised read
for `useSyncExternalStore`. Two things are deliberate:

- an **expired session is not a session** — the same rule on write as on read,
  because the server would refuse it anyway and a page that looked signed in while
  every request 401ed would be worse than one that asks again;
- `hasScope()` is **advisory**: it decides what the UI offers, never what is
  allowed. The server re-derives scopes from the account's current role on every
  request, so a stale client can only ever show a button that fails.

`LoginPage.tsx` is the credential exchange — institution, address, **password** — and
says in the page that no credential mechanism is a decided technology and that the
adapter behind the form is a labelled development mock. It is the **only public
route** (V0-023): `App.tsx` renders the sign-in form for every other page until a
session exists, remembering the requested path in `?next=` and returning there after
a successful sign-in (the redirect is `replace`, and `/login` is never put in
`?next`). There is no longer a `mode.ts`: the development tenant shortcut is off by
default, so a session is the only state the client has, and `hasScope(null, …)` is
`false` for every scope. A `401` that means the server no longer accepts the session
drops it (`api/client.ts`), so the guard re-applies with a truthful state.
`fetchObjectUrl` and every other request carry the session token through
`api/client.ts::send`.

A student who opens a teacher's page is *not* shown a page whose every request
would answer `403`: `StudentNotice.tsx` is a real landing, offering the remembered
class, the class id from their join link, and Sign out. That is a courtesy, not
the control — the server enforces the role on every request.

`frontend/src/student/` is the student's surface, built for the device a student
actually holds. `JoinClassPage.tsx` (`/join/{classId}`) establishes *who is
asking* before anything else: signed out the guard has already sent the browser to
sign in, so the page's signed-out branch is only a defensive fallback; signed in it
shows the class and asks the
server for the caller's own join credential, reporting a refusal by its precise
cause (`NOT_ENROLLED`, `CLASS_NOT_READY`/`NOT_STARTED`, `NOT_FOUND`).
`StudentClassPage.tsx` (`/student/{classId}`, also `/classroom/{classId}`) is the
**fullscreen** view: the slide fills the viewport (a real Fullscreen button as well
as the layout, because a phone browser still shows its own chrome), the controls
keep their ≥44px tap area, and there is **no slide navigation** — the teacher
advances the class and the page follows. It follows the authoritative snapshot by
a quiet ~1.5 s poll; the ordered per-class event stream that would push "the
teacher moved to slide 4" is `DEC-DATA-003` (`OPEN`, live path V1-002). The
narration is the class presenter's **live relayed voice** through
`GET /classes/{id}/narration` (V0-028/V1-005 bridge): the page starts no synthesis,
names the provider (the deterministic development mock or the opt-in OmniVoice
prototype, `DEC-TECH-007` `OPEN`) and offers **Enable sound** when the browser
blocks autoplay. The slide's own text stays behind a collapsed accessibility
disclosure rather than being read as the lesson. What *is* authoritative is the
content: every scene comes from the package the session pinned at start
(`DEC-CONTENT-005`) through `GET /classes/{id}/scenes[/{order}]`, so a correction
published mid-lesson cannot change the slide under the student, and a tampered file
is refused (`SCENE_CHECKSUM_MISMATCH`) rather than shown. When the class ends the
server refuses a student's snapshot/scenes reads with `CLASS_ENDED`, and the page
shows the locked ended screen until a teacher reopens it.

Teacher-side, `admin/ClassesAdmin.tsx` uses the real roster, and V0-022 changed how
a student gets onto it: **the picker chooses from the students who exist** (a
teacher's `account:read` lists students and no other role), and the panel says that
creating an account is the administrator's job in `Admin → Accounts`. Enrolment
never creates an account, so there is no address to type and no implicit signup
behind one; each roster row carries a **Remove** action, and the page says the
account and its sign-in survive a removal. The class detail still offers the
student join link to share.

## Implemented administration and role-aware navigation (V0-022, V0-023)

Three roles sign in through one form (`auth/LoginPage.tsx`), because who you are is
the account's role rather than a choice on a page; and the same page carries the
**first-administrator** panel, since a fresh installation has no accounts at all and
therefore nobody who could sign in to create one. That panel posts to
`POST /auth/bootstrap-admin` with the password the operator chooses, and **fills the
address and password into the sign-in form** so the next step is one click (no secret
is ever returned to display); its refusals are named by cause — the institution
already has an administrator, or a hardened deployment provisions them through the
identity provider instead (`AccountsAdmin.tsx` says the same thing in its
Administrator-accounts panel). The route is gated on `MENTORA_ADMIN_BOOTSTRAP`
(default on), a switch of its own, so a locked installation can still create its
first account.

`admin/AccountsAdmin.tsx` is the directory: create, rename, switch role, disable,
enable and delete teacher and student accounts. **The administrator sets the initial
password on creation and can reset it** (`Reset password`); the password is sent in
the request body, never a query string, and is never echoed back. A reset reports the
live sessions it revoked, because a reset that left them working would not really
have changed who can get in. Two refusals are turned into the remedy they point at,
rather than a raw code: an address that already belongs to the other role says to
change *that* account's role instead of splitting one person in two, and a deletion
refused with `ACCOUNT_IN_USE` says to **Disable** instead, explaining that a removal
would orphan the roster. It never offers to create an administrator — the API refuses
that, so the page does not pretend otherwise.

`Settings → Security` (`settings/SecuritySettings.tsx`) is the holder's own
**change-password** surface: it verifies the current password exactly as a sign-in
does (a wrong one is refused and does not sign you out), sets the new one, and
reports that the account's other live sessions were revoked while this one was kept.

`auth/session.ts` gained the third role, the two new capabilities, `isAdministrator`
(read from `account:write`, never from the role name) and `describeRole`;
`hasScope` answers **false** for every scope with no session (V0-023), because no
session is no capabilities and the development shortcut is off by default.
`components/SiteNav.tsx` therefore chooses its entries by **capability**: an
administrator gets Library, Admin and Settings (they author nothing and attend
nothing, so Studio, Classroom and Learn would only fail), a teacher gets all of
them, and a student keeps their class. `admin/AdminPage.tsx` filters its own
sections the same way and, for a section the role does not hold, says so with links
to the ones it does rather than rendering a page whose every request would 403.

## Implemented responsive layout (phone and large screen)

The app was built for the large screen — a classroom display, a projector, a
laptop in the Teacher Studio — and the UI **MUST** remain usable on a phone
without losing that layout. Every page is therefore one layout expressed
mobile-first, not two designs: `frontend/src/components/ui.tsx` holds the tokens
(tap target, page/card padding, form control, buttons, section tab) and
`frontend/src/components/PageHeader.tsx` is the app bar the five full pages share
(the shared nav, the page's `h1`, an optional qualifier and identifier, the tenant
field and the page's own action).

`lg` (≥1024px) is the switch between the two, and it is not arbitrary: it is
already the app's big-screen breakpoint (every two-column page and the one-row
header use it). Below `lg` the UI assumes a finger, at and above it a mouse:

- A control **MUST** be at least 44px tall below `lg` and may return to the
  original compact height above it. The shared nav is a **wrapping row of chips**
  — six destinations, shown rather than hidden behind a menu — and the section
  tabs (Admin, Settings; four each) wrap onto a second row rather than clipping a
  destination off the right edge, since a four-item strip that hides one item is
  worse than a two-line one.
- A form control **MUST** be 16px below `lg`: iOS Safari zooms the whole page when
  a focused control's text is smaller, and a phone in landscape and a tablet are
  both below `lg`. Above it the original dense size returns.
- A grid container **MUST** declare its own columns at the base breakpoint
  (`grid-cols-*`), and a definition list's value track is
  `minmax(0, 1fr)` rather than `1fr`. A bare `grid` — or an `auto`/`1fr` track
  whose minimum is `auto` — gets a floor of the content's **min-content** width,
  so one long unbreakable value (a deck filename such as
  `updated_B_o_c_o_T_ng_k_t_C_ng_t_c_…`, a SHA-256, a class id) sets the minimum
  width of the container and the page grows wider than the phone instead of the
  value ellipsising. That is not hypothetical: the library page measured 666px
  inside a 390px viewport because `<main>` declared its columns only from `md` up.
  Tailwind's `grid-cols-N` is `repeat(N, minmax(0, 1fr))`, whose floor is 0, so
  declaring the columns **at the base breakpoint** is the fix — a declaration
  behind a variant (`md:grid-cols-2`) is the bug, not the fix.
  `frontend/src/responsive.test.ts` is the source scan for the invariant, because
  jsdom has no layout engine and cannot measure the symptom.
- Definition-list rows (`ui.tsx::Row`) stack label over value on a phone, where a
  long identifier would otherwise be crushed beside its label, and a wide data
  table scrolls horizontally inside its own container rather than squeezing its
  columns.
- The teaching canvas sizes its bitmap to the **device pixel ratio** of the
  surface (`devicePixelRatio`; a phone reports 2–3), so a stroke is drawn at the
  screen's own resolution instead of an upscaled CSS-pixel bitmap. A stroke's
  points and width stay in the surface's **CSS** pixels — the paint transform
  applies the scale — so a stroke keeps its meaning across a re-measure.
  Re-measuring happens on a resize, a rotation and a `ResizeObserver` change.

Nothing about this is a behavioural change: no page gains or loses a control, no
request changes, and the phone layout is the same information the large screen
shows.

The invariant is verified by **measuring the running app in a browser** at 320,
360, 390, 414, 768 and 1280 px: `documentElement.scrollWidth` equals the viewport
on every route, including the densest state (the library with a deck selected, its
stored details, the IR viewer expanded and the raw JSON shown). There is no CI and
no layout test runner in this repository (`FND-001` is `TODO`), so that measurement
is a manual step; `frontend/src/responsive.test.ts` guards the one invariant that
caused a real defect.

## Implemented learning page

`/learn/{artifactId}` (`frontend/src/presentation/`) presents one deck: the
rendered slide, the **teaching canvas** over it, and the slide's teaching script.
The slide is read from the package already built for the deck (never re-rendered
on open) and fetched as an object URL, because `<img src>` cannot send the tenant
header. The teaching canvas (`TeachingCanvas.tsx`) is the client-local core of
the web classroom's dynamic surface: pen, highlighter and eraser, colour, width,
undo and clear, kept per slide for the life of the page. It is **not** shared:
the ordered per-class event stream that would carry an overlay to students is
`DEC-DATA-003` (technology `OPEN`) and its live path is V1-002, so the page says
the annotations stay in the browser rather than faking a broadcast. A browser
with no 2D canvas still shows the slide and reports annotation as unavailable.
The teaching script panel shows the slide's extracted text, its speaker notes,
its lesson-order script from the pinned package and the teacher's newest draft
revision for that section (`GET .../review-package/review-state`).

## Implemented automatic teaching (text only)

The learning page **teaches** as well as shows. `presentation/narration.ts` builds
one narration segment per scene from the deck's *authored* text in a fixed
precedence — the teacher's newest draft revision for the section, else the pinned
package's lesson script, else the slide's speaker notes, else the slide's own text
— and labels which one was used. Nothing is generated and nothing is re-ordered:
there is **no language model** in this path (no LLM provider exists in the
codebase and the decision ledger does not name one), so the feature teaches the
words the author wrote, reproducibly.

Press **Play** and the page narrates: the passage appears as a caption
(`presentation/LearnPage.tsx`, toggleable in Settings) and is appended to a
running transcript, and `presentation/useNarrationTimer.ts` moves to the next slide
once the passage's dwell has elapsed — `dwellMs` scales with the word count and the
teacher's chosen pace (Settings → Teaching) and is clamped to a readable band
(2.5–30 s), so a long passage gets longer and a blank slide still gets a beat.
Pause holds the position, Stop rewinds and clears the transcript, and the last
slide ends the narration rather than wrapping. The timer keys on the segment
identity as well as its length, so two equally long slides do not merge into one
tick, and a re-render cannot restart a countdown.

This is **text only**: no audio is produced. The voice capability is the
provider-neutral speech domain (`backend/app/speech/`, V0-012) and its provider
decision (`DEC-TECH-007`) is `OPEN`, so the text fallback path is the only one that
runs. It is also **client-local**: the narration is not an authoritative event, the
ordered per-class timeline with checkpoints, resume and bridge phrases is
`DEC-RUNTIME-005`/`DEC-DATA-003` and V0-013's work, and the stream that would carry
it to students is V1-002. Nothing about a narration is written to the server.

It can also **start itself at a time the teacher names**: a `datetime-local` value
on the panel, held as an instant by the page's own clock (`time.ts`, `useNow`), and
when that instant arrives the narration begins — Pause, Stop, the caption and the
transcript then behave exactly as if Play had been pressed. The trigger is
client-local for the same reason the narration is: it is a page waiting, not a
server clock, so the tab has to stay open, and the panel says so. Moving it
server-side is exactly the durable workflow/timeline work that is `DEC-TECH-003`
(`OPEN`) and V0-013.

## Implemented admin and settings areas

`/admin/{section}` (`frontend/src/admin/`) manages the V0 entities **through the
existing API only** — overview (what the tenant holds), accounts (the directory,
V0-022), courses & materials (create a course, upload a deck into it, compile it,
open its Studio/learning page), classes (schedule, start, assign and remove
students) and publications (publish, verify). The write verbs are the domain's own
transitions; there is no generic update or delete *of content*, and that is a
property of the domain rather than a gap: content is immutable, a draft is
append-only and a publication is never deleted (`DEC-CONTENT-005`), so a correction
is a new version. An **account** is the exception that proves the rule — a name, a
role and an enabled state are genuinely mutable — so the directory has a real
rename, role switch, disable/enable and removal, with removal refused while a class
references the account. The publications view is the place the seal is made
visible: `Publish` is idempotent on the content and reports a replay as such, and
`Verify integrity` re-checks the pinned package against the digest recorded at seal
time and reports `VERIFIED`/`MISMATCH`/`MISSING` without mutating anything.

The section list itself is filtered by **capability** (V0-022), so the tabs a
principal sees are exactly the ones the server would allow.

A class can be given a **datetime**, and the classes view shows it and how far off it
is, ticking on the page's own clock (`time.ts`). With **auto-start** on, a class whose
time has come is started while the page is open, through the same idempotent
`POST /classes/{id}/start` the Start button uses, and each outcome is reported per
class — including a refusal, so a class whose course was never published says
`CLASS_NOT_READY`/`VERSION_NOT_PUBLISHED` instead of appearing to have started. This
is deliberately **not** a server scheduler: the backend records `scheduled_for` and
never acts on it (an automatic start would be a durable workflow, and `DEC-TECH-003`
is `OPEN`), so nothing runs with the page closed, the view states that, and Start
stays available either way.

`/settings/{section}` (`frontend/src/settings/`) holds **client preferences**,
because there is no settings API: the server's own configuration is its environment
(the home region) and the per-request render mode. General reports the tenant
(a real input, sent as `X-Institution-Id`) alongside read-only server facts
(`GET /renderer`, `GET /health`) and the home region; Rendering persists the
compile/preview mode and probes the renderer live in that mode (`GET
/artifacts/{id}/renders/{order}?mode=`), stating that a **packaged** render is
pinned at build time; Teaching sets the narration pace, autoplay and captions and
whether a scheduled class is started when its time arrives; Accessibility edits the
**classroom's own** persisted preferences through the classroom store, so the two
never drift. Preferences live in one module
(`settings/store.ts`, persisted and shared across tabs like the tenant) and are
never authoritative — nothing in Settings changes what the server stores, seals or
publishes.

## Locked Decisions Implemented

- `DEC-RUNTIME-004`
- `DEC-TURN-002`
- `DEC-TURN-009`


<!-- SOURCE: 16_DATA_STORAGE_AND_EVENTS.md -->

# Data, Storage, and Events

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define durable truth, projections, ordering, and retention.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Durable relational store owns institution/course/publication/session/checkpoint/academic records. Ordered log stores per-class commands/events. Redis stores routing/projection/cache/revocation, never sole truth. Object storage stores immutable binaries; search is rebuildable.

Use transactional outbox to avoid database/event dual write. Delivery may be at-least-once; logical effects are idempotent. Raw student audio is off by default; retention policies are separate by data class.

## Locked Decisions Implemented

- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-003`
- `DEC-DATA-004`


<!-- SOURCE: 17_SECURITY_PRIVACY_AND_GOVERNANCE.md -->

# Security, Privacy, and Governance

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define trust boundaries, authorization, threats, and institutional controls.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

OIDC/OAuth users, workload identity services, short-lived least-privilege tokens, tenant/resource authorization. Threats include cross-tenant access, replay, split brain, malicious documents, prompt injection, RAG poisoning, voice misuse, leakage, and operator abuse.

Controls include sandboxing, provenance, schema validation, pre-retrieval authorization, epoch-fenced tokens, dedup, secrets/network policies, audit, data minimization, consent, residency, provider/model registry, retention/export/deletion, and incident response.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-TURN-008`
- `DEC-DATA-005`
- `DEC-RELIABILITY-002`
- `DEC-RUNTIME-007` (V0-021: a session is honoured against its current role, and revocation is checked on every read)

## Implemented identity boundary (V0-021)

Full detail is in `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`. The part
that belongs to the trust boundary:

- **The tenant is derived, never supplied.** A request's tenant comes from the
  session the API resolves; `X-Institution-Id` is the *development* shortcut
  (`MENTORA_DEV_TENANT_HEADER`, default **off** as of V0-023, so a request with no
  session is `401 SESSION_REQUIRED`) and is ignored whenever a session is present. A
  caller can therefore never widen its own institution by naming one.
- **Sign-in is required, and the credential is a password (V0-023).** Every route
  except `/health`, `/auth/login` and the one-shot bootstrap answers only to a
  session; the frontend renders the sign-in form for every other page until a
  session exists, and returns to the page that was requested. The password is set by
  the administrator at creation and reset, or changed by the holder through
  `POST /auth/password`; it travels in a request **body**, never a URL. Setting or
  resetting it revokes the account's live sessions (`DEC-RUNTIME-007`), while a
  self-service change keeps only the caller's. The minimum length is a development
  guard, not a decided policy.
- **Authorization is a capability, checked at the route.** Every verb on every
  router carries `require(scope)`; `ROLE_SCOPES` is the single place a role's
  capabilities are decided. No route is protected only by its client.
- **Least privilege is enforced where it is decided.** A student session carries
  `class:read`, `scene:read` and `join` and nothing else; it cannot publish, write
  content, review, or read the roster. The reciprocal holds too: `join` is the
  student's **participant** capability, so a teacher holds none and is refused
  where a participant identity is required. A join credential carries `subscribe`
  only (`DEC-TURN-001`).
- **Administration is a role of its own, not a super-teacher (V0-022).** An
  institution administrator holds `account:read`, `account:write`, `content:read`
  and `class:read` — the directory and read-only oversight — and nothing that
  authors, teaches or attends. A teacher gains `account:read` but may list and read
  **students only**, because choosing students for a roster is not reading the staff
  directory. Creating an account (`account:write`) and enrolling one
  (`enrollment:write`) are separate capabilities, so neither is implied by the
  other: **enrolment never creates an account**, and an unknown address is a named
  refusal rather than an implicit signup.
- **An identity a class used is deactivated, not deleted.** Removing an account that
  any class roster references is refused (`409 CONFLICT`, `ACCOUNT_IN_USE`) and the
  remedy is to disable it; removal is guarded rather than cascading so a roster and
  the history behind it cannot be orphaned. Disabling **revokes live sessions in the
  same call** (`DEC-RUNTIME-007`), reporting how many.
- **The account directory is `OPEN`-free and self-limiting.** An administrator
  cannot create or change another administrator (`ROLE_NOT_MANAGEABLE`); the first
  one comes from a one-shot deployment bootstrap gated on its own switch
  (`MENTORA_ADMIN_BOOTSTRAP`, default on), and refuses once the tenant is
  provisioned. Nothing here is presented as the decided account-provisioning
  mechanism — with institutional federation the identity provider owns it.
- **Credentials and tokens are stored as digests.** A session stores
  `sha256(token)`; a credential stores scrypt digest + per-account salt. Neither
  raw value is retrievable after the response that issued it.
- **No enumeration oracle.** An unknown account and a wrong credential are the
  same stable code and the same timing (a dummy salt is verified either way).
- **A refusal is not a fault.** Installed-capability unavailability is `503
  AUTHENTICATION_UNAVAILABLE`; a rejected credential is `401
  AUTHENTICATION_FAILED`; a missing principal is `401 UNAUTHENTICATED`; a missing
  capability is `403 INSUFFICIENT_SCOPE`. Clients and tests can tell them apart
  (`DEC-RELIABILITY-002`).
- **The stand-in is visible.** The credential adapter is a labelled
  `DEVELOPMENT_MOCK` and says so in every response and in the client UI; the
  mechanism is not a decided technology and is not presented as one.


<!-- SOURCE: 18_ACCESSIBILITY_AND_INCLUSION.md -->

# Accessibility and Inclusion

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define equivalent participation and accessible presentation.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

All classroom controls are keyboard accessible with screen-reader state announcements and predictable focus. Captions/transcript, adjustable speech speed, reduced motion, contrast, non-color semantics, scene alternatives, accessible quizzes, and typed-question fallback are required.

Partial student transcript is ephemeral and clearly marked; final visibility follows policy. Prerecorded media needs reviewed synchronized captions and meaningful non-speech information.

## Locked Decisions Implemented

- `DEC-TURN-009`


<!-- SOURCE: 19_RELIABILITY_SLO_AND_BACKPRESSURE.md -->

# Reliability, SLO, and Backpressure

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define bounded latency, overload behavior, and fallback.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Candidate targets: control p95 <250ms, hand ACK <300ms, floor-to-mic <1s, audio cancel <300ms, end-turn to first answer audio p95 <5s, presentation drift <200ms, recovery <10s, resume >99.5%, invariant violations zero.

Reserve scarce capabilities before granting user-visible permission. Bound queues per tenant/provider/class. Propagate end-to-end deadline/cancellation. Retry transient idempotent work only. Circuit breakers trigger cached script, neutral voice, text/captions, typed question, or controlled pause.

## Locked Decisions Implemented

- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`


<!-- SOURCE: 20_OBSERVABILITY_COST_AND_CAPACITY.md -->

# Observability, Cost, and Capacity

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define experience metrics, tracing, cost, and scaling units.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Propagate trace, tenant, class, session, command, correlation/causation, epoch/version, and artifact versions while redacting sensitive text/audio.

Measure actor/state/invariant, queue/floor/STT/VAD, LLM/RAG/TTS, marker drift, WebRTC network, compiler fidelity/review, recovery and cost. Define Teaching Compute Unit empirically from actor and AI duty cycles. Alert immediately on invariant breach and use SLO burn alerts.

## Locked Decisions Implemented

- `DEC-RELIABILITY-001`
- `DEC-DEPLOY-002`


<!-- SOURCE: 21_TESTING_CHAOS_AND_ACCEPTANCE.md -->

# Testing, Chaos, and Acceptance

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Make architecture correctness executable.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Unit reducers, property invariants, schema/consumer contracts, provider conformance, persistence/outbox integration, browser/media E2E, load/soak, chaos/DR, security, accessibility, and content fidelity.

Chaos includes actor death/network partition, stale callbacks, Redis restart, DB failover, SFU loss, late audio, STT final loss, TTS marker loss, slow/cancelled RAG/LLM, token replay, and capacity saturation. Pass requires safe degradation and zero invariant breach.

## Locked Decisions Implemented

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`


<!-- SOURCE: 22_DEPLOYMENT_AND_SCALING.md -->

# Deployment and Scaling

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define deployment profiles and measured scale progression.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Profiles: managed cloud, institution cloud, hybrid, private/on-prem. V1 control plane modular monolith; separately scalable compiler, media, search, STT/LLM gateways, GPU voice.

A class has a home region for actor/gateway/SFU/STT/voice path. Drain nodes without terminating active classes. Validate 10, 50, 100, 250, 500 classes only after previous profile passes, separated by student count and interaction duty cycle.

## Locked Decisions Implemented

- `DEC-DEPLOY-001`
- `DEC-DEPLOY-002`


<!-- SOURCE: 23_LMS_SIS_SCORM_AND_INTEGRATIONS.md -->

# LMS, SIS, SCORM, and Integrations

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define institutional integration boundaries.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Identity and LMS adapters synchronize launches, courses, rosters, deep links, and approved outcomes with explicit field ownership/conflict policy. Official records are not inferred by LLM.

SCORM manifest/organizations/sequencing may be structurally imported. Interactive non-convertible SCO runs in isolated origin/iframe with CSP, restricted network/API, and compatibility adapter. Never claim universal native conversion.

## Locked Decisions Implemented

- `DEC-SCORM-001`


<!-- SOURCE: 24_ROADMAP_AND_REPOSITORY.md -->

# Roadmap and Repository

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define phased delivery and code/document organization.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

V0: deterministic PPTX, scene/CTF baseline, browser, typed question, neutral voice. V1: Actor, ordered commands, Raise Hand/floor/STT, audio ACK, checkpoint, pinned RAG. V2: group media/reveal/video/moderation/accessibility/cloned voice. V3: institution integration/governance/DR/pilot. V4: measured regional scale.

Repository keeps canonical architecture, decision governance, executable contracts, state/sequence/data/provider/security/operations/tests, and source code together. No phase advances without invariant, load, recovery, security, accessibility, and cost gates.

## Locked Decisions Implemented

- `DEC-DEPLOY-001`


<!-- SOURCE: 25_IMPLEMENTATION_CHECKLIST.md -->

# Implementation Checklist

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Provide the final architecture compliance gate.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Before coding list requirement IDs, locked/open decisions, owners, states, commands/events, schemas, data, provider deadlines, retry/cancellation/fallback/recovery, security/privacy/accessibility, telemetry, tests, rollback.

Every mutation has authority, authn/authz, ordering key, command ID, epoch/version, invariant validation, transaction/outbox, effect idempotency, response, metric, timeout, retry, and recovery.

Completion requires contract/migration validation, invariant/property/integration/E2E/chaos tests, telemetry/alerts, review gates, traceability update, and no unresolved contradiction.

## Locked Decisions Implemented

- `DEC-RUNTIME-003`
- `DEC-RELIABILITY-001`
