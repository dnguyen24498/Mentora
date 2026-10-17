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

## Locked Decisions Implemented

- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-DATA-001`
- `DEC-DATA-002`


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

Record engine/version/fonts/warnings/provenance and classify native-compatible-structural-degraded-failed. Failed blocks publication; degraded meaning requires review.

Two local render modes sit behind the renderer interface while the production renderer technology is `OPEN`:

- **`themed` (default)** keeps the author's layout (every object is drawn where and at the size the source put it) and re-styles it in a platform-controlled theme: typeface, palette, and slide chrome are the platform's, not the source deck's. Its fidelity is `THEMED_RENDERED` — a re-styling, **not** a rank on the fidelity-to-source ladder — and the gate is re-scoped from visual fidelity to *content completeness*: nothing is re-selected, re-ordered, or clipped (an `a:noAutofit` text frame spills exactly as PowerPoint spills it), `TEXT_OVERFLOW:` is reported per object rather than losing lines in silence, and the theme owns its typefaces so an unavailable source font cannot degrade a scene. Source colours are mapped onto the theme palette *by role*, so a light-on-dark pair stays light-on-dark.
- **`faithful`** reproduces the source slide's own geometry and styling and reports `STRUCTURAL_RENDERED`.

An object that cannot be re-styled (a chart, SmartArt) degrades the scene (`UNSUPPORTED_OBJECT:`) and requires review rather than being silently flattened. The renderer never reads the source package: it receives the Content IR and the picture bytes the compiler injects (`DEC-CONTENT-001`).

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

Scene includes stable ID/source, normalized dimensions/bounds, fallback render, structured objects, notes, refs, fidelity, warnings, provenance, and steps. Stable object identity changes referenced by lessons require review.

## Fidelity classification

`fidelity` records **how** a scene's fallback render relates to its source, and every scene carries exactly one value:

| Value | Meaning |
| --- | --- |
| `NATIVE_RENDERED` | produced by a native/compatible engine (no such engine is accepted yet) |
| `COMPATIBLE_RENDERED` | produced by a compatible engine (no such engine is accepted yet) |
| `STRUCTURAL_RENDERED` | the source slide's own geometry and styling reproduced structurally |
| `THEMED_RENDERED` | the author's layout, re-styled in the platform theme (typeface, palette, chrome) |
| `DEGRADED_RENDERED` | renderable, but a human check of meaning is required |

`THEMED_RENDERED` is deliberately **not** on the fidelity-to-source ladder: nothing is claimed about the original appearance, so consumers must not read it as "better" or "worse" than `STRUCTURAL_RENDERED`. It is still an explicit, non-native classification, never a native render. Its content-completeness alarm is `TEXT_OVERFLOW:<object>`: the author's text frame does not hold its text (an `a:noAutofit` box where a whole line lands past the frame's bottom edge), which is drawn as PowerPoint draws it (spilling, never clipped) and degraded for review. Text that merely dips a few pixels past a tight frame is normal typography and is not degraded. A failed render is a `FAILED` *status*, not a fidelity, and blocks publication.

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

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
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

## Locked Decisions Implemented

- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-008`
- `DEC-DEPLOY-002`


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
