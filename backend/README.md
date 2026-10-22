# Backend (modular monolith)

Python backend for the AI Teacher Platform. The V0 vertical implemented so far:
**secure PPTX ingestion + SQLite-backed persistence + deterministic structural
extraction + per-slide rendering that reproduces the deck's own styling, behind
an explicit fidelity gate + a baseline Content Package + teacher review**
(preview, approve/reject, draft lesson-order and script edits) **+ atomic
publication + class scheduling and start with an exactly pinned runtime tuple
and a durable initial snapshot + real accounts and authorization** (teacher and
student sign-in behind a provider-neutral seam, teacher-invited enrolment, and a
student's own view of the class it pinned).

## Commands

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
env -u PYTHONPATH .venv/bin/python -m pytest -q          # all tests
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_pptx_extractor.py -q   # one file
```

`env -u PYTHONPATH` is required in this shell (ROS 2 sets a global `PYTHONPATH`
that breaks the venv's `pytest`).

Run the API on `:8001` (the frontend dev server uses `:8000`; tenant is passed
as `X-Institution-Id` until OIDC is wired):

```bash
cd backend
env -u PYTHONPATH .venv/bin/uvicorn app.api.app:create_app --factory --reload --port 8001
```

The server also serves the built frontend at `/` when `frontend/dist/` exists
(optional single-origin mode; override the location with `MENTORA_FRONTEND_DIST`).
It is mounted through `app/api/spa.py` (`SpaStaticFiles`), which answers the
frontend's client-side routes — `/studio/{artifactId}` included — with the app
shell, so a deep link or a refresh works there too; a real asset is still served
as itself and a **missing** asset still 404s (rewriting it to HTML would only
break the browser). For normal development the frontend runs on its own server at
`:8000` — see `frontend/README.md`.

## Layout

| Path | Responsibility |
| --- | --- |
| `app/security/` | Upload validation: size limit, filename normalization, extension + magic-byte checks (stable error codes). |
| `app/storage/` | `ObjectStore` interface + atomic, content-addressed `LocalObjectStore`. |
| `app/courses/` | Course/version/source-artifact/compiler-job models, tenant-scoped repository, `UploadService`. |
| `app/compiler/models/` | Internal Content IR (`content-ir/1.2.0`): scenes, objects, effective style (fill/line/geometry/text), text runs, media refs, normalized bounds, fidelity, provenance. |
| `app/compiler/extractors/` | Dependency-free PPTX (OOXML) structural extractor (`PptxExtractor`): theme/master/layout resolution (`theme.py`, `style.py`) + `ooxml.py` part/name helpers. |
| `app/compiler/renderers/` | Provider-neutral `DocumentRenderer` adapter + two deterministic local SVG renderers behind a mode factory — faithful/structural (default, V0-005/V0-018) and themed (opt-in, V0-019) — plus the theme (`mentora_theme.py`) and a required test double. |
| `app/compiler/validators/` | Scene/package invariants and the fidelity publication gate (V0-005) plus CTF package validation (V0-006). |
| `app/compiler/render_service.py` | `RenderingService`: artifact -> Content IR -> per-slide render (mode-selected) -> gate. |
| `app/compiler/package_builder/` | Baseline Content Package builder (V0-006): IR + renders -> scenes/lesson plan/manifest, plus `read_package` for reading one back. |
| `app/compiler/service.py` | `ExtractionService`: artifact -> Content IR -> job status. |
| `app/publication/` | Teacher review of a built package (V0-007, `review.py`/`workflow.py`/`draft.py`) **and** the atomic publication transition (V0-008, `service.py`/`seal.py`/`index.py`/`outbox.py`): seal (checksums + digests) → index-version pin → one commit transaction → published-version retrieval. `auto.py` composes build → auto-approve (only for an auto-allowed `READY` package) → publish for the Library upload flow; a human-required package is returned unpublished. |
| `app/classroom/` | Classes, runtime session plans and sessions (V0-009): schedule a class, start it by resolving and pinning the exact runtime tuple once (`service.py`/`repository.py`/`catalog.py`), build and validate the durable initial snapshot (`snapshot.py`), and authorize joins against the class enrollment. **V0-010** adds `aggregate.py` — the in-process `ClassroomAggregate` reducer (`START`/`NAVIGATE_SCENE`/`CHECKPOINT`/`END`/`REOPEN` commands, command-id dedup, epoch/state-version fencing, snapshot round-trip) — with `navigate_scene`/`record_checkpoint`/`end_class`/`reopen_class` service methods and `repository.py::commit_transition`. **V0-025** adds the teacher's slide command: `navigate_to_order` resolves a pinned scene order against the package's scene list and lesson plan (`scene_source.py::lesson_plan`) and sends the aggregate a resolved `NAVIGATE_SCENE`; the student view reads the resulting snapshot by a short poll, not an ordered stream. **V0-027** closes the lifecycle: `END` locks a completed class's content for participants, and `REOPEN` (`COMPLETED → ACTIVE`) runs the **same** class occurrence again from its first slide under a **new actor epoch**, keeping the roster and the pinned package. |
| `app/classroom/timeline/` | **V0-013 narrated presentation + V1-005 bridge**: the pinned script is cut into word-safe chunks and synthesized per chunk (`stream.py`), with the `TimelineController` state machine, script precedence and the NDJSON teacher stream. `relay.py` fans the teacher's **already-generated** generation out to enrolled students through `GET /classes/{classId}/narration` (in-process, best-effort; no per-student synthesis), replaying the current slide's buffered chunks to a late joiner and superseding it on the next slide. Not the SFU media plane. |
| `app/speech/` | **V0-012 neutral voice (domain)**: the provider-neutral `SpeechProvider` port (+ `CancelToken`/`SpeechBudget`), the speech models, the `SpeechService` (reserve → synthesize → cancel → release, with neutral-voice then text fallback), classified errors, structured telemetry, and a scripted fault-injection test double. Imports nothing outside itself and the stdlib. |
| `app/identity/` | **V0-021/V0-022 identities (domain)**: the `Authenticator` port, accounts/roles/scopes (`ROLE_SCOPES` is the one place a role's capabilities are decided; `institution_admin` is one of the three roles, and `MANAGEABLE_ROLES`/`TEACHER_LISTABLE_ROLES` say who an administrator creates and who a teacher may list), tenant-scoped digest-only repositories, `IdentityService` (login never raises; `create_account`/`update_account`/`delete_account`/`bootstrap_administrator`), stable error codes, telemetry and a test double. Imports nothing outside itself and the stdlib. |
| `app/providers/` | **Replaceable capability adapters**: `deterministic.py` — the one neutral-voice adapter V0 runs with (`neutral-deterministic@1.0.0`, dependency-free and deterministic) — `local_credentials.py` (`local-credentials@1.0.0`, `kind="DEVELOPMENT_MOCK"`: stdlib `scrypt` digest-only credentials, timing-parity on an unknown address) and `factory.py` (`create_speech_provider`/`build_speech_service`, `create_authenticator`/`build_identity_service`). |
| `app/db/` | SQLite connection handling (`Database`: one connection per thread) + schema/migration application. |
| `app/api/` | FastAPI app factory; `security.py` resolves the principal and enforces capabilities (`require(scope)`), `identity_router.py` serves `/auth/*` (including the one-shot first-administrator bootstrap) and `accounts_router.py` serves the account directory (`/accounts`, V0-022, composed with the classroom service for the roster guard); serves the built frontend at `/` when present, with an SPA fallback for client-side routes (`spa.py`). |
| `app/common/` | Base errors and stable error codes. |

## Endpoints

Every route below requires a principal and a capability (V0-021/V0-022), so `401 UNAUTHENTICATED` (`issue_code SESSION_REQUIRED`) and `403 INSUFFICIENT_SCOPE` (`issue_code SCOPE_REQUIRED`) apply to all of them. A request may present either a **session token** (`Authorization: Bearer <token>`) or, while the development tenant shortcut is on, the `X-Institution-Id` header alone. `POST /auth/login` is the exception (it takes its institution in the body, since that is what the credential proves), and so is `POST /auth/bootstrap-admin`, which is unauthenticated by necessity.

- `POST /auth/bootstrap-admin` — **V0-022/V0-023**: create the institution's **first** administrator, once, with the **password** it will sign in with. Unauthenticated because there is no administrator yet to authorize it; gated on its **own** setting `Settings.admin_bootstrap` (`MENTORA_ADMIN_BOOTSTRAP`, default on), so a locked installation can still create its first account and a hardened deployment does not expose it (`404 NOT_FOUND`, `issue_code BOOTSTRAP_DISABLED`); `409 CONFLICT` with `issue_code TENANT_ALREADY_PROVISIONED` the moment the tenant has an administrator, and writes nothing on either refusal. With institutional federation the identity provider provisions that account, so this is a development seam, not the platform's provisioning mechanism. JSON body `institution_id`, `email`, `password`, optional `display_name` — a password never travels in a URL.

- `POST /auth/login` — **V0-021/V0-023**: exchange a **password** (`institution_id`, `email`, `password`) for a session. **Never raises on a bad credential**: it returns `ok: false` with `AUTHENTICATION_FAILED` — and the same code and timing for an unknown address as for a wrong password, so the endpoint is not an account oracle. Success returns the raw `token` (only `token_sha256` is stored), the `principal`, the `authenticator` capability (labelled `DEVELOPMENT_MOCK`) and `expires_at`.
- `POST /auth/password` — **V0-023**: change the signed-in account's own password. JSON body `current_password`, `new_password`; the current one is verified exactly as a sign-in is, so a wrong one is `401 AUTHENTICATION_FAILED` (`issue_code INVALID_CREDENTIALS`) and the caller's session **stays valid**. A new password below `MIN_CREDENTIAL_LENGTH = 8` is `400 INVALID_REQUEST` (`issue_code CREDENTIAL_TOO_WEAK`). On success every **other** live session of the account is revoked and the caller's is kept.
- `GET /auth/me` — the principal the presented session authorizes, plus `admin_bootstrap` (whether the one-shot first-administrator route is exposed). With no session and the development shortcut explicitly on and a valid tenant header it reports the shortcut: `authenticated: false`, no account, `development_shortcut: true`. With the shortcut off (the shipped default) it is `401 SESSION_REQUIRED`.
- `POST /auth/logout` — revoke the presented session (a `revoked_at` write the next read honours, `DEC-RUNTIME-007`); idempotent.
- `GET /accounts?role=` — **the account directory (V0-022)**, requires `ACCOUNT_READ`, and `role` (`teacher`|`student`) is **required** so the read cannot drift into an accidental directory dump. A caller without `ACCOUNT_WRITE` (a teacher) may list **students only** (`TEACHER_LISTABLE_ROLES`) and is refused `403 INSUFFICIENT_SCOPE` (`SCOPE_REQUIRED`) for any other role. An unknown role name is `400 INVALID_REQUEST`.
- `POST /accounts` — **create a teacher or a student**, requires `ACCOUNT_WRITE`. JSON body `email`, `role`, `password`, optional `display_name` (a password never travels in a URL). **Create-or-link**: the same address and role returns the existing account with `created: false` and `credential_set: false` (**a retry never overwrites the holder's password**, `DEC-RUNTIME-003`); the same address with another role is `409 CONFLICT` (`issue_code EMAIL_ROLE_CONFLICT`); a role this surface does not manage — including `institution_admin` — is `409 CONFLICT` (`issue_code ROLE_NOT_MANAGEABLE`), because an administrator cannot create a peer. Returns `{created, account, credential_set, sessions_revoked}`; the password is stored only as a digest and is never returned.
- `GET /accounts/{accountId}` — one account, requires `ACCOUNT_READ`, with the same restriction as the list: without `ACCOUNT_WRITE` only a **student** account may be read. Another institution's account is `403 TENANT_ACCESS_DENIED` (the tenant exists; the account is not the caller's), an unknown id is `404`.
- `PATCH /accounts/{accountId}` — **change a display name, a role, the enabled state or the password**, requires `ACCOUNT_WRITE`. JSON body `display_name`, `role`, `status` (`ACTIVE`|`DISABLED`), `password`; an omitted field is unchanged, and an unknown `status` is `400 INVALID_REQUEST`. **Disabling — and setting or resetting the password — revokes the account's live sessions in the same call** (`DEC-RUNTIME-007`) and reports `sessions_revoked`; re-enabling restores sign-in. A **role change only ever removes** capabilities from a live session (the session's stored scopes are intersected with the issuing role), so a promotion takes effect at the account's next sign-in.
- `DELETE /accounts/{accountId}` — **remove an account**, requires `ACCOUNT_WRITE`. Refused while **any class roster** in the tenant references it: `409 CONFLICT` (`issue_code ACCOUNT_IN_USE`), and the remedy is `PATCH status=DISABLED` — removal is guarded rather than cascading, so a roster and the audit history behind it cannot be orphaned. An unreferenced account is removed together with its credential material and sessions in one transaction; an unknown id is `404`.
- `POST /courses` — create a course; `title` query param, optional `course_id`.
- `GET /courses` — list the tenant's courses (used by the frontend picker).
- `GET /courses/{courseId}/materials` — list the course's uploaded presentations, newest first, each with its version number and compiler-job status (used by the frontend file list).
- `POST /courses/{courseId}/materials` — multipart `file`; returns `202` with artifact/job/version ids. Duplicate bytes (or a repeated `Idempotency-Key`) return the existing record with `created: false`.
- `POST /artifacts/{artifactId}/extract` — runs structural extraction and returns the Content IR.
- `POST /artifacts/{artifactId}/compile` — extraction + a fallback render for every slide + the fidelity gate; returns `content_ir`, `render`, `validation`, `job_status`. Idempotent. `?mode=faithful|themed` picks the render mode (V0-019 v5, default `faithful`); an unknown mode is `400 INVALID_REQUEST` (`UNKNOWN_RENDER_MODE`).
- `GET /artifacts/{artifactId}/renders/{order}` — the deterministic fallback visual (SVG) for one slide, re-derived from the stored artifact and tenant-scoped. `?mode=` as above.
- `POST /artifacts/{artifactId}/review-package` — **V0-007**: builds the Baseline Content Package (V0-006, idempotent) and returns the teacher review view — per-slide render reference, extracted text, notes, warnings/fidelity and the fallback lesson order with safe markers. `409 PUBLICATION_BLOCKED` when the fidelity gate failed, so a blocking failure is never reviewable.
- `GET /artifacts/{artifactId}/review-package` — the review view of the **stored** package; never re-renders (~20 ms for a 28-slide deck vs ~4 s to build). `404` when nothing is built yet.
- `GET /artifacts/{artifactId}/review-package/renders/{order}` — one slide's packaged fallback render, served from the package (no re-render) after the manifest confirms it lists the asset.
- `POST /artifacts/{artifactId}/review-package/decision` — **approve or reject** the built package. `400 INVALID_REQUEST` for a rejection without a reason, `409 PUBLICATION_BLOCKED` when the document is not publishable (so a blocking failure cannot be approved), `404` when no package exists. Idempotent for a repeated identical action; returns the resulting review state.
- `GET /artifacts/{artifactId}/review-package/review-state` — the current decision, the newest draft revision, the draft count, the course-version status, and whether the decision is `stale` (recorded for a different content version).
- `POST /artifacts/{artifactId}/review-package/drafts` — **append a draft revision** of the lesson order. The body's array order is the proposed order and every entry must name a section that already exists in the package, so a draft can only reorder and re-script; structural fields are inherited from the package. `400` with an `issue_code` (`EMPTY_DRAFT`, `UNKNOWN_SECTION`, `DUPLICATE_SECTION`, `MISSING_SECTION`, `INVALID_SCRIPT`) when it is not a rearrangement, `409 REVISION_CONFLICT` when a concurrent save won the revision.
- `GET /artifacts/{artifactId}/review-package/drafts` — draft revision history, newest first.
- `POST /artifacts/{artifactId}/auto-publish` — the Library upload shortcut: builds the package, and when the review policy marks it auto-allowed (`READY`, no human-required scene) records the signed-in teacher's approval and publishes it in one call. A `REVIEW_REQUIRED` package returns `published: false` with its review state and is left for Teacher Studio; a blocking failure is `409 PUBLICATION_BLOCKED`. Replaying the same content returns the existing publication with `created: false`. Requires `content:write`, `review:write` and `publication:write` together.
- `POST /course-versions/{versionId}/publish` — **V0-008**: seal the built package (verify checksums/references, record the manifest and content digests), establish the compatible knowledge-index version, and commit the publication + index pin + outbox event in **one transaction**; returns the publication with `created`. Idempotent on `(versionId, content_package_version)`: a replay returns the same publication with `created: false`. `409 PUBLICATION_BLOCKED` with an `issue_code` (`NOT_APPROVED`, `STALE_APPROVAL`, `WRONG_STATE`, the validator's code, `INDEX_FAILED`) when the version must not be published; nothing is written. `404` when no package is built.
- `GET /course-versions/{versionId}/publication` — the version's newest publication (`404` when unpublished). `?verify=true` re-reads the pinned package and re-checks it against the digest sealed at publish time, adding an `integrity` report (`VERIFIED`/`MISMATCH`/`MISSING`).
- `GET /publications/{publicationId}` — one publication by identity, **including a superseded one** (a session pinned to it keeps reading it). Another institution's is `404`, not `403` (the lookup is tenant-scoped and does not leak existence). `?verify=true` as above.
- `GET /courses/{courseId}/publications` — the course's publication history, newest first, superseded ones included (`?limit=`, default 50).
- `POST /classes` — **V0-009**: schedule a class against a course (`course_id` required, optional `title`, `version_id`, `scheduled_for`). Created `SCHEDULED`; `version_id` must be a version *of that course* (`400 INVALID_REQUEST` otherwise). `scheduled_for` is recorded but never enforced — there is no scheduler (`DEC-TECH-003` `OPEN`), so the start is explicit.
- `GET /classes` — the tenant's classes, newest first (`?limit=`, default 100). **For a student it is scoped to their roster** (V0-024): only the classes they are enrolled in, because the roster is what authorizes a join and the institution's whole schedule is not theirs to read. A teacher and an institution administrator still see all of them.
- `GET /classes/{classId}` — the class with its `session` and `session_plan` (both `null` before a start). A student is a participant, so their read is limited to a class on their roster (`403 NOT_ENROLLED`); staff read by capability.
- `POST /classes/{classId}/start` — **V0-009**: resolve the exact runtime tuple **once** — course/version/publication/package/content, lesson plan, knowledge-index pin, policy, capability, home region — pin it immutably and commit the initial durable snapshot with the session in **one transaction**, then go `ACTIVE`. `200` with `created` (false on a replay): a duplicate or concurrent start returns the same session (`DEC-RUNTIME-003`). `409 CLASS_NOT_READY` with an `issue_code` — `VERSION_NOT_PUBLISHED` (draft/never published), `INCOMPATIBLE_INDEX` (the index pin is not about this content), `INCOMPATIBLE_CONTENT` (envelope/lesson plan the runtime does not support, or the package is missing), `CONTENT_DIGEST_MISMATCH` (the pinned bytes no longer match the seal), `WRONG_STATE`, `COMMIT_CONFLICT` — and nothing is written, so the class stays `SCHEDULED` and retryable.
- `GET /classes/{classId}/snapshot` — the authoritative session snapshot, validated (schema version + checksum) before it is returned; a damaged one is `502 STORAGE_FAILURE` with `issue_code SNAPSHOT_INVALID` rather than being replayed. `404` when the class has not started. A student's read is checked against the class roster (`403 NOT_ENROLLED`); after the class has ended it is refused `409 CLASS_NOT_READY` with `issue_code CLASS_ENDED` until a teacher reopens it (V0-027) — the class metadata and list stay readable. The student view polls this document to follow the teacher's current scene (V0-025 — a short poll, not the V1-002 stream).
- `POST /classes/{classId}/navigate` — **V0-025**: the teacher's presentation control (requires `CLASS_WRITE`). The JSON body names the pinned scene `order` (optional `expected_state_version` fence and `command_id` idempotency key). The server resolves the order against the session's **pinned** scene list and lesson plan, then sends the aggregate a resolved `NAVIGATE_SCENE`; no source deck is parsed and no current publication is consulted (`DEC-CONTENT-001`, `DEC-CONTENT-005`). `200` returns the verdict, the updated session and the durable snapshot (`snapshot: null` on a duplicate — nothing new was written). `409` refusals write nothing: `CLASS_NOT_READY`/`NOT_STARTED` before a start, `CONFLICT`/`STALE_STATE_VERSION` when the caller's view is behind, `CONFLICT`/`INVALID_TRANSITION` after the end, `CONFLICT`/`INCOMPATIBLE_CONTENT` when the pinned plan does not name the scene. This is an HTTP command over the existing aggregate, **not** the ordered per-class live stream (`DEC-DATA-003` remains `OPEN`, V1-002).
- `POST /classes/{classId}/end` — **V0-027**: the teacher ends the class (requires `CLASS_WRITE`). Runs the aggregate's `END` (`ACTIVE`/`DEGRADED → COMPLETED`), writes the final checkpoint in the same snapshot, and revokes the session's join tokens. Optional JSON body carries only the `expected_state_version` fence and `command_id` idempotency key. `200` returns the verdict, the session and the snapshot (`snapshot: null` on a duplicate). A second end is `409 CONFLICT`/`INVALID_TRANSITION`; a stale view is `409 STALE_STATE_VERSION`. After the end the class is shown as **Ended** and its content is locked for students (`CLASS_ENDED`), while staff read by capability.
- `POST /classes/{classId}/reopen` — **V0-027**: reopen an ended class (requires `CLASS_WRITE`). `COMPLETED → ACTIVE` for the **same class occurrence**: the roster and the pinned version tuple are kept (`DEC-CONTENT-005`), the lesson returns to its first position from the pinned lesson plan, and a **new `actor_epoch`** is started, so every pre-end credential and fenced command is stale (`DEC-RUNTIME-007`). Optional `expected_state_version`/`command_id` as above. `409` refusals write nothing: `CONFLICT`/`INVALID_TRANSITION` when the class has not ended, `CLASS_NOT_READY`/`NOT_STARTED` before a start, `CONFLICT`/`INCOMPATIBLE_CONTENT` for a damaged pinned plan, `CONFLICT`/`STALE_STATE_VERSION` for a stale view. A genuinely new lesson is a new class; a reopen is deliberately not a second occurrence.
- `POST /classes/{classId}/enrollments` — **enrol a student** (requires `ENROLLMENT_WRITE`). Two mutually exclusive query params: `email` resolves an account **that already exists in this tenant** and `student_id` names one by id (an id that is not one of this tenant's accounts is `404`, never a free-text roster entry). **Enrolment never creates an account** (V0-022): an address this institution has no account for is `404 NOT_FOUND` with `issue_code ACCOUNT_REQUIRED` — an institution administrator creates accounts, a teacher assigns them. Idempotent per `(class, student)`: returns `{...enrollment, created, student}`. The class is validated before the student is resolved, and a refusal writes nothing.
- `GET /classes/{classId}/enrollments` — the class roster, with the account behind each enrolment. Requires `ENROLLMENT_WRITE` because the roster is other people's identities.
- `DELETE /classes/{classId}/enrollments/{studentId}` — **remove a student from the roster** (requires `ENROLLMENT_WRITE`), idempotent (`DEC-RUNTIME-003`). A roster correction, **not** an account change: the account, its sessions and any credential it already holds are untouched. What ends immediately is the ability to obtain a **new** join credential, because the join check reads this roster.
- `POST /classes/{classId}/bootstrap-token` — **V0-009/V0-021**: issue a join credential to **the caller's own account**, so the request has **no body** — a caller cannot ask for someone else's join. Joining is a *participant* action, so it requires the `join` capability, which the student role holds and the teacher role does not: a teacher, and the development tenant shortcut (which is a teacher principal), is refused `403 INSUFFICIENT_SCOPE` before the class is read. For a student it requires an `ACTIVE` or `DEGRADED` session **and** a tenant-scoped enrollment of that account: `403 NOT_ENROLLED` when the caller is in the tenant but not enrolled; `403 TENANT_ACCESS_DENIED` for another institution's class; `409 CLASS_NOT_READY` with `issue_code NOT_STARTED` before a start, or `issue_code CLASS_ENDED` after the end (V0-027). The raw token is returned once — only its `token_sha256` is stored — and it binds class/student/session/`actor_epoch`/nonce/expiry with `subscribe` scope only.
- `GET /classes/{classId}/scenes` — **V0-021/V0-025**: the slides of **the package this session pinned at start** (never the course's current publication, `DEC-CONTENT-005`), each with its `order` (0-based), `scene_id`, `fidelity`, `text`, `notes`, `warnings`, `object_count` and `step_count`. The student viewer uses it to gather the current slide's own text; it does **not** offer slide navigation. A student's read is checked against the class roster (`403 NOT_ENROLLED`) and refused with `409 CLASS_ENDED` after the class ends (V0-027).
- `GET /classes/{classId}/scenes/{order}` — one slide's packaged render (SVG), served **through the package manifest**: a path the manifest does not list is not readable (so this cannot become an arbitrary object read, `DEC-CONTENT-004`) and the bytes are re-checked against the digest the manifest recorded — a swap is `502 STORAGE_FAILURE` with `issue_code SCENE_CHECKSUM_MISMATCH` rather than a presentation. A student's read is checked against the class roster (`403 NOT_ENROLLED`) and refused with `409 CLASS_ENDED` after the class ends (V0-027).
- `GET /classes/{classId}/narration/{order}` — **V0-013**: the teacher's narrated presentation stream for one pinned scene (requires `CLASS_WRITE`). The pinned script is cut into word-safe chunks and synthesized by the provider-neutral voice; the body is newline-delimited JSON with `narration.started`, per-chunk `segment.started`/`caption`/`audio` (base64 WAV)/`marker`/`segment.completed`, and a terminal verdict. `expected_state_version` fences a stale view before any synthesis; closing the connection cancels it. The provider is the deterministic mock while `DEC-TECH-007` is `OPEN`.
- `GET /classes/{classId}/narration` — **V1-005 bridge**: the enrolled student's **live relay** (requires `SCENE_READ`, plus the class roster for a student). It starts no synthesis and reads no source document; it attaches to the generation the teacher's tab is currently producing and copies the same WAV chunks, so a class does not pay one provider call per learner. `204` means there is no current generation (the teacher is paused, has not started narrating yet, the student is on another scene, or the page passed the generation it already consumed); a `200` stream begins with that generation's `narration.started`, replays the chunks already buffered for that slide, then carries the chunks published while attached, and ends at its terminal verdict. The current slide is the unit of replay, so a late joiner hears it from its start; a completed generation stays replayable for a short TTL, `after_generation` suppresses replaying the same slide, and `expected_scene_id` keeps the audio under the scene the snapshot shows. An ended class is `409 CLASS_ENDED`; this is an **in-process development relay**, not the SFU media plane (`DEC-TECH-004` remains `OPEN`), so it is single-process and best-effort and persists no audio.
- `GET /renderer` — the default render mode, every available mode, the active theme, and the requested mode's identity/capability/circuit-breaker health (`?mode=`, V0-019).
- `GET /artifacts/{artifactId}` — artifact metadata (the Teacher Studio uses `filename` for its page title).
- `GET /health`.
- `GET /` — the built frontend (when `frontend/dist/` exists). Any other
  extension-less path returns the same app shell, because the frontend routes
  client-side (`/studio/{artifactId}`); unknown JSON API paths keep their own
  error responses.

## Design notes / deliberate deviations

- **SQLite** is used as the V0 local/dev equivalent of the durable relational
  store required by `DEC-DATA-001` ("PostgreSQL **or equivalent**"). The schema
  is isolated in `app/db/schema.sql` so the repository layer can target
  PostgreSQL later; the PostgreSQL reference is `database/migrations/0001_baseline.sql`,
  `database/migrations/0002_review_decisions_and_drafts.sql`,
  `database/migrations/0003_atomic_publication.sql`,
  `database/migrations/0004_class_and_session_plan.sql` and
  `database/migrations/0005_identity_and_accounts.sql`.
- **Connections are thread-scoped (V0-020).** FastAPI serves the sync endpoints
  from a worker threadpool, so requests really do overlap. A `sqlite3.Connection`
  cannot be shared for that: `BEGIN`/`COMMIT` state and cursors are
  connection-scoped, so two requests on one connection interleave (one request's
  `BEGIN` lands inside another's transaction; a cursor is consumed while another
  thread runs a statement on it). `Database` hands each thread its own connection
  while repositories keep calling the same `self._conn.execute(...)` and
  `transaction(self._conn)`. Each connection sets `PRAGMA busy_timeout` (5 s), so a
  queued writer waits for SQLite's write lock instead of failing with
  `database is locked` — bounded failure (`DEC-RELIABILITY-001`), not a hang.
  `tests/test_database_concurrency.py` holds this contract: 240 concurrent
  read+write requests must all succeed and every reported write must be visible.
- Extraction lives under `app/compiler/` (modular monolith). Task `V0-004`
  nominally targets a top-level `compiler/` package; within `app/compiler/` the
  layout follows the task's areas (`models/`, `extractors/`, `renderers/`,
  `validators/`). Relocate to a top-level package if/when the compiler is split
  out of the monolith.
- **`.pptx` (OOXML) only.** Legacy binary `.ppt` (and `.pptm`/`.ppsx`) is
  rejected with the stable code `UNSUPPORTED_LEGACY_FORMAT` rather than
  misparsed; no macro/script/OLE is ever executed.
- The extractor uses only the stdlib (`zipfile` + `xml.etree`) and bounds archive
  expansion (`ARCHIVE_TOO_LARGE`) to resist zip-bomb/malicious-archive threats.
- **Groups**: a `p:grpSp` holds its shapes as *immediate children* (there is no
  nested `p:spTree` inside a group). The extractor emits a `group` object and
  flattens its contents; nested groups are traversed. Containers it does not
  model (e.g. `p:contentPart`, `mc:AlternateContent`) produce an
  `unsupported element` warning instead of being dropped silently.
- **The tenant always comes from a credential, never from a request field.** With a
  session, `X-Institution-Id` is ignored and the tenant is the session's; with no
  session it is only the development shortcut below, which is off by default. Every
  repository call is tenant-scoped and cross-tenant access is rejected.
- **The credential mechanism is not a decided technology (V0-021/V0-023).** The
  spec's requirement is institutional federation, and every identity-provider/token
  decision in the ledger is `OPEN`; `FND-002` (the identity ADR) is still `TODO`.
  So `app/identity/` defines the `Authenticator` port, and the only registered
  implementation is an explicitly-labelled development stand-in
  (`app/providers/local_credentials.py`, `local-credentials@1.0.0`,
  `kind="DEVELOPMENT_MOCK"`): stdlib `hashlib.scrypt`, per-account salt,
  **digest-only** storage, and a constant dummy-salt verification so an unknown
  address and a wrong password are the same code **and** the same timing (no
  enumeration oracle). A caller supplies the secret — the administrator on create
  and reset, the holder on change — and the adapter never mints or returns one; the
  API therefore reports `credential_set: bool`, never a credential value. The
  response carries `authenticator.kind` so the stand-in is visible on the wire,
  exactly as the renderer and the neutral voice do for their own open decisions. An
  OIDC/OAuth adapter is a second implementation of the same ABC; nothing in the
  domain changes when one arrives.
- **The tenant is a session claim, and a session is required (V0-023).** With a
  session, `X-Institution-Id` is ignored and the tenant comes from the session, so a
  caller cannot widen its own institution by naming one. `X-Institution-Id` alone is
  the **development tenant shortcut** (`MENTORA_DEV_TENANT_HEADER`, default **off**):
  with it explicitly on it resolves a *teacher* marked `authenticated: false` with no
  account; off (the shipped default) every route without a session is `401
  SESSION_REQUIRED`. It cannot join a class even when on, because joining is the
  student's participant capability and the shortcut is a teacher — the guard refuses
  it `403 INSUFFICIENT_SCOPE` (`SCOPE_REQUIRED`).
- **Authorization is a capability, re-derived per request.** `app/api/security.py::require(scope)`
  guards every verb on every router, and a session's stored scopes are
  **intersected** with what the account's role currently grants on every read — so
  narrowing a role takes effect on the next request rather than at session expiry,
  a role change can only ever remove a capability (never hand a live session one it
  was not issued), and `join` belongs to the student role alone, so a teacher or the
  development shortcut is refused where a participant identity is required. A
  session is revoked by a `revoked_at` write the same read honours
  (`DEC-RUNTIME-007`). A missing principal is `401 UNAUTHENTICATED`; a missing
  capability is `403 INSUFFICIENT_SCOPE` — distinct from `AUTHENTICATION_FAILED`
  (a rejected credential) and `AUTHENTICATION_UNAVAILABLE` (`503`, the capability
  could not be reached — an availability failure, never a denial,
  `DEC-RELIABILITY-002`).
- **Administering identities and assigning them are different jobs (V0-022).** Three
  roles are modelled — `institution_admin`, `teacher`, `student` — and
  `ROLE_SCOPES` decides each one's capabilities. An institution administrator holds
  the directory (`account:read`, `account:write`) plus read-only oversight
  (`content:read`, `class:read`), and **nothing** that authors, teaches or attends:
  they are not a super-teacher. A teacher gains `account:read` but may list and read
  **students only** (`TEACHER_LISTABLE_ROLES`), because filling a roster picker is
  not reading the staff directory. `account:write` (create an account) and
  `enrollment:write` (assign one) are separate, so **enrolment never creates an
  account** — an unknown address is `404 ACCOUNT_REQUIRED`, not an implicit signup.
  `MANAGEABLE_ROLES` excludes `institution_admin`, so an administrator cannot create
  or promote a peer (`409 ROLE_NOT_MANAGEABLE`): the first administrator comes from
  the one-shot `POST /auth/bootstrap-admin`, which is absent unless the development
  shortcut is on and refuses once the tenant is provisioned — under federation the
  identity provider owns that account. Disabling revokes live sessions in the same
  call; removal is refused while a class roster references the account
  (`409 ACCOUNT_IN_USE`) and the remedy is to disable, so a roster and its history
  are never orphaned. The roster guard is composed in `app/api/accounts_router.py`
  (the identity domain never learns about classrooms), and every verb is
  tenant-scoped from the **session**.
- **The class reads what it pinned.** `GET /classes/{id}/scenes[/{order}]` resolve
  the session's own `RuntimeSessionPlan`, not the course's current publication, so
  a correction published mid-lesson cannot change the slide a student is looking
  at (`DEC-CONTENT-005`); each served file is read only because the package
  manifest lists it and is re-checked against the digest the manifest recorded
  (`SCENE_CHECKSUM_MISMATCH`), so scene serving is neither an arbitrary object read
  nor a way to present tampered bytes.
- **The renderer is not a decided technology.** `DEC-TECH-005` ("Native
  PowerPoint rendering deployment and licensing") is `OPEN`, so
  `docs/adr/proposed/ADR-P005_RENDERER.md` applies: *"Until accepted,
  provider-neutral interfaces and mocks are used."* `app/compiler/renderers/`
  therefore defines the `DocumentRenderer` interface, a required test double, and
  two dependency-free local implementations behind it (`renderers/factory.py`
  selects by mode) — neither is ever reported as native/compatible:
  - **`faithful` (default, V0-019 v5)** — `StructuralSvgRenderer` reproduces the
    **source slide's own layout and styling** (V0-018) and reports
    `STRUCTURAL_RENDERED`: the effective theme colours and font scheme, backgrounds
    (including a layout's **picture** background — resolved against the layout's own
    relationships), the art the slide **inherits** from its layout/master (V0-019 v7),
    preset + `custGeom` shapes, fills/strokes/dashes, rotation/flip, real font sizes
    with wrap/alignment/bullets, embedded pictures with crop, tables and connectors.
    A component it cannot reproduce is **drawn in the platform look, in place**
    (`renderers/mentora_theme.py`), never dropped and never a review blocker:
    an unavailable source font is *substituted* with the platform's type stack
    (deterministically — the client's fonts cannot change the asset) and recorded
    as `FONT_SUBSTITUTED:<family>`, and a frame whose font was substituted is shrunk
    to stay inside the author's frame instead of spilling over its neighbour; a
    chart/SmartArt/WordArt/equation/graphic frame becomes a flat platform panel
    labelled with the object (`UNSUPPORTED_OBJECT:<kind>`); a picture that cannot be
    inlined (EMF/WMF/TIFF, over budget, bytes withheld) becomes a flat platform
    panel labelled with the part. Keeping the author's layout also means keeping the
    author's overlaps: where a source deck's own frames overlap, the overlap is
    reproduced, exactly as PowerPoint shows it.
  - **`themed` (opt-in, V0-019 v4)** — `ThemedSvgRenderer` **keeps the author's
    grouping and re-authors the look**: the grouping and content are the author's,
    the arrangement within each group and the appearance are the platform's
    (`renderers/flow.py` + `renderers/textmetrics.py` + `renderers/mentora_theme.py`),
    reporting `THEMED_RENDERED`. A binary widest-gap XY-cut over the source boxes
    recovers the slide's rows and columns (an icon stays beside its label; a column
    is only cut when both sides are a substantial share of the region), and each
    recovered cell is folded into flow blocks (a merged list of paragraphs, a
    table, a row of pictures) placed by a single measuring pass over a cursor:
    position and measurement are the same computation, so blocks cannot overlap by
    construction (`tests/test_flow_layout.py` asserts the invariant pairwise over
    the emitted geometry). A row cell that draws more than one block becomes a
    card: the content is inset and a flat surface panel (no border) is painted
    behind it. A heading is hoisted (kicker/title/subtitle over one
    hairline rule) and the page number lives in a reserved bottom strip the flow
    may not enter. The look is entirely the platform's: its type stack, its type
    scale, its palette; no source typeface, colour, fill or geometry is
    reproduced. The gate is therefore **content completeness**, and no code path
    can lose content: nothing is re-selected, re-ordered, or dropped, and content
    that cannot be fitted even at the smallest readable type scale is still drawn
    (flagged `TEXT_OVERFLOW:<scene>`, degraded for review, page number omitted so
    nothing is covered). An object that cannot be redrawn (chart, SmartArt) becomes
    a labelled panel and degrades (`UNSUPPORTED_OBJECT:`). The theme is versioned
    and folded into the renderer's config hash, so a theme change is a new
    content-package version.
  - `?mode=faithful|themed` selects the mode on `POST /artifacts/{id}/compile` and
    `GET /artifacts/{id}/renders/{order}`; `GET /renderer` reports the default, all
    modes, the active theme, and the requested capability (an unknown mode is a
    `400 INVALID_REQUEST`/`UNKNOWN_RENDER_MODE`). The package cache key binds the
    renderer identity (`name@version`), so a themed package can never be mistaken
    for a faithful one. Replace these behind the interface once FND-002 records the
    decision.
- **Fidelity gate**: every slide gets a render or an explicit `FAILED`;
  `FAILED`/`CANCELLED`/missing renders make the document non-publishable
  (`PUBLICATION_BLOCKED`, wired into `POST /course-versions/{id}/publish`'s
  contract for V0-008). `DEGRADED_RENDERED` scenes require review. A component the
  default renderer draws in the platform look, and a source font it had to
  substitute, are **warnings** on a structural scene — greppable
  (`FONT_SUBSTITUTED:<family>`, `UNSUPPORTED_OBJECT:<kind>`, `UNSUPPORTED_MEDIA:`,
  `MEDIA_BUDGET_EXCEEDED:`, `MEDIA_UNAVAILABLE:`) and disclosed in the review's
  `missing_fonts`/`warnings`, but they do **not** set `requires_review`, because
  nothing is missing from the output.
- **Faithful slide rendering (V0-018, the default mode since V0-019 v5).**
  `DEC-TECH-005` is still `OPEN`, so this is explicitly *not* a native PowerPoint
  engine: the renderer draws the presentation **from the Content IR**. Fidelity
  comes from extraction, not from a new dependency — the IR resolves the deck's
  effective look (theme colours and fonts through `p:clrMap`, slide→layout→master
  placeholder geometry and `p:txStyles` defaults, backgrounds,
  fills/lines/gradients/geometry/rotation, run+paragraph formatting, `srcRect`
  crops, table metrics) and the renderer reproduces it in SVG. Consequences worth
  knowing:
  - **Backgrounds cascade across parts, and their images belong to the part that
    declares them.** A deck's art-directed (usually dark) backgrounds live on the
    title/section **layouts**, so each level resolves against its own
    relationships; an unresolvable picture fails through to the next background up
    with a warning instead of blanking the slide. Missing that turns a dark closing
    slide into white-on-white.
  - **A slide also draws what its layout and master contribute** (V0-019 v7).
    Decks keep their shared chrome — the crest, the faculty badge, a rule, a static
    label — on the **layout**, not on every slide, and PowerPoint paints it *under*
    the slide's own objects. Extraction collects the **non-placeholder** art of the
    master and the layout (`inherited_objects`, each part resolved against its own
    relationships, `showMasterSp` honoured on the slide and on the layout) and the
    renderer paints it master-first, layout-second, the slide's own objects last. A
    layout/master placeholder is not art — it is a definition the slide's own
    placeholder replaces — and inherited objects are not slide content: they never
    join `objects`, the slide's text, its reading order or its `object_count`.
    Without this the reference deck's 26 slides lose the top-right logo pair they
    carry only in the layout. Because the parts are the author's, a high-resolution
    logo is inlined at its source resolution on every slide that inherits it
    (reference deck: ~500 KB per slide) — the per-scene budget is what bounds it,
    and the opt-in `themed` mode does not carry the chrome at all.
  - The IR must stay self-sufficient: a renderer that opened the `.pptx` would
    break `DEC-CONTENT-001`, so image bytes travel separately in
    `RenderRequest.media`, keyed by the IR's `media_ref`.
  - Pictures are inlined as `data:` URIs (the studio shows the SVG through a
    `blob:` `<img>`, where external references cannot resolve). A per-scene raw
    budget (`RenderConfig.max_inline_media_bytes`, 16 MiB) and an output cap
    (`max_asset_bytes`, 28 MiB) keep one slide from bloating the package. A
    picture that cannot be inlined (over budget, EMF/WMF/TIFF, or bytes not
    supplied) is drawn as a **flat platform panel** labelled with the part
    (`renderers/mentora_theme.py`) and warned about
    (`MEDIA_BUDGET_EXCEEDED:`/`UNSUPPORTED_MEDIA:`/`MEDIA_UNAVAILABLE:`) — in place,
    without changing fidelity.
  - **A component the source cannot be reproduced for is drawn in the platform
    look, in place** (the product rule is *"same layout as the author's deck;
    where a component cannot be reproduced, draw it in the platform's default
    look"*): an unavailable source font is substituted with the platform's type
    stack — deterministically, so the client's own fonts can never change the asset
    — and recorded as `FONT_SUBSTITUTED:<family>`; a chart/SmartArt/WordArt/
    equation/graphic frame is a flat platform panel labelled with the object
    (`UNSUPPORTED_OBJECT:<kind>`); an unknown preset geometry is its bounding
    rectangle. None of these lowers the fidelity or sets `requires_review`: the
    content is complete and the layout is the author's.
  - Text uses estimated glyph advances for word-wrap and auto-shrink (an
    auto-fitting box is never overrun; an `a:noAutofit` box that does not hold its
    text spills, as PowerPoint spills it), and a frame whose font was *substituted*
    is shrunk to stay inside the author's frame rather than spilling over a
    neighbouring block — our metrics are not the author's. There is no font metric
    library in the stdlib, so a substituted typeface can wrap a line a word earlier
    than PowerPoint would.
  - Because the author's geometry is kept, the author's *overlaps* are kept too:
    where a source deck's own frames overlap, the render reproduces the overlap,
    exactly as PowerPoint shows it.
  - The renderer identity is bumped to `3.0.0` and the IR schema to
    `content-ir/1.2.0`; both are part of the cache key, so stale renders are not
    reused after this change. (V0-019 v7 draws inherited layout/master art, so the
    identity moves on to `local-structural-svg@3.1.0` and the extractor to `1.4.0`,
    which retires packages built before it.)
- **Themed slide rendering (V0-019 v4, opt-in since v5).** `ThemedSvgRenderer`
  re-authors the *look* of each slide while keeping the *grouping* and every word,
  cell and picture the author put on it. It shares only the
  `_Canvas`/`_attr`/`_num` helpers with the structural renderer; its geometry is
  `flow.py`'s, not the source's:
  - **The grouping is the author's**: the IR objects keep their source boxes, and
    a binary widest-gap XY-cut (`flow.structure`) recovers the slide's rows and
    columns. A cell holds the objects the author grouped together, so an icon
    stays beside its label and a card keeps its parts. A column is only cut when
    both sides are a substantial share of the region width
    (`theme.min_column_share`), so a narrow icon column never splits from its
    label; a full-width object spans the region and forbids a column cut through
    it. Same-key neighbours (one bullet per text box) are re-joined into one run.
  - **Content is the author's**: each recovered cell is folded into flow blocks — a
    list of paragraphs (level indent, bullet markers when the source resolved one,
    bold/italic runs), a table (empty rows/columns dropped, source column
    proportions kept), a row of pictures (≤4 per row, aspect from the file
    header), a panel for a chart/SmartArt. A text-less decorative shape is dropped
    (it is not content).
  - **The look is the platform's**: the theme's type stack, its type scale, its
    palette (`mentora_theme.py`). Source sizes only choose a *row* (`lead`/`body`/
    `caption`, relative to the slide's most common size), so an art-directed
    statistic still reads as one. No source colour, fill, stroke or box is drawn.
    A cell that draws more than one block becomes a **card**: the content is inset
    and a flat `theme.surface` rounded panel (no border) is painted behind it.
  - **Placement is the platform's**: within a cell, blocks are measured and placed
    in the same pass, so a block always advances the cursor and can never overlap
    the next. A hoisted heading (kicker/title/subtitle + one hairline rule) sits
    above the body and the page number below it, in a strip the flow cannot enter.
  - **The gate is content completeness**: nothing is re-selected, re-ordered or
    dropped. Content that does not fit even at the smallest readable scale is
    still drawn in full and flagged `TEXT_OVERFLOW:<scene>` (degraded for review,
    page number omitted). A chart/SmartArt is a labelled panel plus
    `UNSUPPORTED_OBJECT:` and review — in this mode only; the default mode draws
    it in the platform look in place and merely warns. No LLM rewrites slide text,
    because that would change meaning.
  - **Metrics are estimated** (`textmetrics.py`: a font-free Helvetica/Arial advance
    table biased slightly wide), so a line may break a word early — it can never
    push a block into its neighbour. There is no bundled font to license or embed.
  - The theme is versioned and folded into the renderer's config hash; the
    renderer identity is `mentora-themed-svg@4.0.0`, so themed and faithful
    packages can never be confused.
- Rendering is deterministic and content-addressed: identical bytes + identical
  renderer identity/config produce byte-identical SVG, so recompiles reuse one
  asset. Job claiming, leases, checkpoints, and stage persistence are V0-003 and
  are not implemented here; `RenderingService` is a re-runnable stage function.
- **Baseline Content Package (V0-006).** `PackageBuildService.build()` runs the
  *baseline builder* stage: it renders (V0-005), enforces the fidelity gate, then
  maps the Content IR into the package described by `contracts/ctf/*.schema.json`
  — one scene document per slide, the fallback render copied in as a
  content-addressed asset, a fallback lesson plan (one section per scene, speaker
  notes verbatim, safe markers `<scene_id>#step-<n>`), and a manifest with
  checksums. The manifest is written **last** and is the commit point; all
  references inside the package are package-relative, so no consumer needs the
  compiler's asset store or an OOXML parser. `contracts/ctf/PACKAGE_LAYOUT.md` is
  the layout/reference contract; determinism, integrity, and negative cases are
  covered by `tests/test_package_builder.py`. There is deliberately **no HTTP
  endpoint** yet (the task's writable area is the compiler library); the
  teacher-facing preview is V0-007, publication is V0-008.
- **Teacher review (V0-007).** `app/publication/review.py` projects the *stored*
  package into the review view, so what the teacher sees is exactly what the
  runtime would receive, and browsing costs no rendering. The package id is
  derived from the same cache key as `content_package_version`
  (`pkg-<digest16>`), so identical content always resolves to one package prefix:
  a retried build completes the same package instead of duplicating it, and a
  read-only consumer can address a package without any server state. A document
  that failed the fidelity gate answers `409 PUBLICATION_BLOCKED` instead of being
  offered for review.
- **Review actions and drafts (V0-007).** `app/publication/workflow.py` records
  the two things a teacher can *change*, and neither touches the package:
  a **decision** (approve/reject) and a **draft revision** of the lesson order.
  Approving moves the course version to `APPROVED` and rejecting returns it to
  `REVIEW_REQUIRED` — review states only. The publication transition
  (`APPROVED → SEALING → INDEXING → COMMITTING → PUBLISHED`), the pinned index and
  the outbox are V0-008 (below). A decision binds to the `content_package_version` it
  reviewed, so a rebuild under different content/config reports it as `stale`
  rather than letting it pass as current. Drafts are append-only revisions
  (`UNIQUE (artifact_id, revision)`), their structural fields (`scene_id`,
  `scene_step_id`, `safe_markers`, `type`) are inherited from the package under
  review, and the built package is byte-identical after any edit — which is what
  "edits create draft data, not mutate published package" means in practice.
  Both are durable relational state (`review_decisions`, `review_drafts` in
  `app/db/schema.sql`; PostgreSQL reference
  `database/migrations/0002_review_decisions_and_drafts.sql`), written in one
  transaction each, so a failure changes nothing and retrying is safe.
  `app/publication/telemetry.py` emits `publication.review.decided` /
  `publication.review.draft_saved` with counts and lengths only — a review reason
  and an edited script are never logged. Reviewer identity is client-supplied and
  is **not** an authorization control: roles arrive with the identity work in
  `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`.
- **Atomic publication (V0-008).** `app/publication/service.py` runs the three
  stages and then one commit. The stages are **in-process and never persisted**, so
  there is no staging row a crash could leave behind: "partial publication is
  invisible" holds by construction, not by compensation. **SEALING** (`seal.py`)
  re-validates the stored package and computes two digests — `manifest_sha256`
  (the envelope, kept for provenance) and `content_digest` (path + SHA-256 of every
  manifest-listed file, sorted), which is the *verify* basis, so a legitimate
  rewrite of the manifest (a new `created_at`) is not a false alarm. **INDEXING**
  goes through the replaceable `IndexBuilder` interface (`index.py`):
  `BaselineIndexBuilder` establishes the index-version identity a publication must
  pin (`DEC-DATA-005`) and builds no index content — a Baseline Content Package is
  usable without enrichment (`DEC-CONTENT-002`) and the search/vector technology is
  `OPEN` (`DEC-TECH-008`), so it pins `unindexed` and records the published
  `content_digest` as the content it is compatible with. V0-014 replaces the
  builder; the record, the pin and the transaction do not move. **COMMITTING**
  (`repository.py::PublicationRepository.commit`) is one transaction that writes
  the index-version row, the publication row and the transactional-outbox row,
  performs the guarded `APPROVED → PUBLISHED` status change (the row count is the
  guard) and marks superseded publications — so a visible publication always has
  its pin and its event.
  - **Identity is content**, `(version_id, content_package_version)`, unique per
    tenant: a replay returns the *same* publication with `created: false`, and two
    concurrent publishes of one version produce exactly one (the loser re-reads the
    winner; an unrecoverable race is a classified `COMMIT_CONFLICT`). The existence
    check runs *before* the approval check, because a replay arrives when the
    version is already `PUBLISHED`, which is not the `APPROVED` precondition.
  - **A correction is a new course version** — new package, new publication.
    Publishing it marks the course's strictly older publications, and any other
    publication of the same version, `SUPERSEDED` with a `superseded_by` link.
    Nothing is deleted: `DEC-CONTENT-005` pins all compatible versions, and
    `GET /publications/{id}` serves a superseded one to the session reading it.
  - **Refusals are classified and write nothing** (`errors.py`): `409
    PUBLICATION_BLOCKED` with `NOT_APPROVED`, `STALE_APPROVAL`, `WRONG_STATE`, the
    validator's own code (e.g. `CHECKSUM_MISMATCH`) or `INDEX_FAILED`. Every one is
    raised before the transaction, so the version stays retryable
    (`DEC-RELIABILITY-002`).
  - **The seal is the read half of immutability**: `?verify=true` on either read
    endpoint re-reads the *pinned* prefix (not the one the current renderer
    implies) and reports `VERIFIED`/`MISMATCH`/`MISSING` against the recorded
    digest rather than erroring.
  - Durable state: `publications`, `knowledge_index_versions` and
    `publication_outbox` in `app/db/schema.sql` (PostgreSQL reference
    `database/migrations/0003_atomic_publication.sql`). The outbox row is written
    but **not dispatched** — delivery technology is `OPEN` (`DEC-TECH-001`), so
    `dispatched_at` stays null until a later task adds a sender.
    `app/publication/telemetry.py` emits `publication.stage`,
    `publication.published`, `publication.blocked` and
    `publication.integrity_checked` with the version tuple and counts only — never
    slide text, notes or a review reason. Covered by
    `tests/test_publication_publish.py` (19): the happy path, the index pin and its
    provenance, the outbox event (and its JSON-Schema contract), duplicate and
    concurrent publish, a crash at each stage (nothing published, retry succeeds),
    checksum and index failure, a stale/absent approval, publishing writing no
    bytes, a correction leaving the old package readable, tamper detection, tenant
    isolation, and telemetry.
- **Class and runtime session plan (V0-009).** `app/classroom/` schedules a class and
  starts it by resolving and pinning the exact runtime tuple **once**.
  - **The module home is `app/classroom/`.** The task family's own allowlists name it
    (V0-010 → `classroom/`, V0-013 → `classroom/timeline/`, V1-004 → `classroom/turn/`),
    so the reserved legacy placeholders `class_management/`, `session/` and
    `student/` are left empty rather than split across four packages.
  - **`PREPARING` is in-flight only and is never persisted**, the same reasoning as
    V0-008's stages: one transaction (`ClassRepository.commit_start`) performs the
    guarded `UPDATE classes … WHERE state = 'SCHEDULED'` (the row count is the guard)
    and then writes the plan, the session and the initial snapshot. A crash anywhere
    leaves the class `SCHEDULED` with no plan/session/snapshot, so a partial start is
    invisible by construction and the retry is another `POST …/start`.
  - **No runtime `latest` lookup — the tuple is resolved once and pinned.** With no
    `version_id` the start takes the course's current *published* publication; with
    one it takes that version's publication, superseded included (`DEC-CONTENT-005`).
    The plan (`RuntimeSessionPlan`) has no update path, so publishing a correction
    afterwards leaves a running session's tuple *and* snapshot byte-identical while a
    later class pins the newer version — `tests/test_class_start.py` proves both
    halves.
  - **Named absences in the tuple.** `assessment_version` and `model_routing_version`
    are pinned as explicit `null`s: the canonical tuple names them and V0 has neither
    subsystem, and recording the absence means the immutable tuple never has to gain
    a field later.
  - **The runtime half is replaceable infrastructure.** `catalog.py` defines the
    `RuntimeCatalog` interface and a baseline that supplies `policy_version`
    (`runtime-policy@1`, the name of the applied LOCKED default policy set), the
    supported CTF envelope versions (`1.0.0`) and the home region from
    `Settings.home_region` (`MENTORA_HOME_REGION`, default `local-1`). `DEC-TECH-009`
    is `OPEN`, so the region is configuration and no cloud geography is asserted.
    `capability_version` is the *observed* identity of the warmed default renderer
    (`name@version`, full identity kept in the plan's `capabilities`), so a later
    renderer upgrade cannot retroactively change what a session warmed.
  - **The start reads only what it pins.** It re-verifies the pinned package against
    its seal (`seal.verify_package`) and reads its manifest + `lesson-plan.json`, and
    it reads the publication's knowledge-index record — never the source `.pptx`
    (`DEC-CONTENT-001`) and never a re-render. The index pin is checked for
    *compatibility*, not mere presence: `index_version` must equal the publication's
    `knowledge_index_version` and `source_digest` must equal its `content_digest`
    (`DEC-DATA-005`).
  - **Refusals are classified and write nothing.** `409 CLASS_NOT_READY` with
    `issue_code` = `VERSION_NOT_PUBLISHED` (a draft or never-published version),
    `INCOMPATIBLE_INDEX`, `INCOMPATIBLE_CONTENT` (unsupported envelope/lesson plan, or
    a missing package), `CONTENT_DIGEST_MISMATCH` (the pinned bytes no longer match
    the seal), `WRONG_STATE`, `COMMIT_CONFLICT`; the join path adds `NOT_STARTED`.
    `403 NOT_ENROLLED` is the class-participation denial (distinct from the
    cross-tenant `403 TENANT_ACCESS_DENIED`). A damaged snapshot is
    `502 STORAGE_FAILURE` + `SNAPSHOT_INVALID`. Two new stable `ErrorCode` members;
    `PUBLICATION_BLOCKED` stays the publication transition's own code.
  - **Duplicate and concurrent starts are idempotent** (`DEC-RUNTIME-003`): the class
    is the identity, so the second request returns the first session with
    `created: false`, and `UNIQUE (class_id)` on the plan and the session is the
    backstop for a race the guard missed (the loser re-reads the winner, or is
    classified `COMMIT_CONFLICT`).
  - **The snapshot is durable and validated before use** (`DEC-DATA-004`):
    `snapshot.py` builds one canonical document (`runtime-snapshot@1`; pinned versions,
    lesson position from the pinned plan, empty `turn.queue`/null floor, null timeline
    checkpoint, no pending effects, `actor_epoch`/`state_version`/`event_sequence` = 1)
    with a sha256 checksum over its canonical bytes, stored beside the document.
    `GET /classes/{classId}/snapshot` re-validates schema version *and* checksum and
    refuses a damaged document rather than replaying it.
  - **Join is authorized, not assumed.** `POST /classes/{classId}/bootstrap-token`
    requires an `ACTIVE` session and a tenant-scoped enrollment **of the caller's
    own account** — since V0-021 it takes no body, so there is no student id to
    assert; the credential binds class/student/session/`actor_epoch`/nonce/expiry,
    is stored **only** as `token_sha256`, carries `subscribe` scope only
    (`DEC-TURN-001`), and `verify_bootstrap_token` refuses
    unknown/expired/revoked/stale-epoch tokens (`DEC-RUNTIME-007`). It has no
    media-gateway route yet (the gateway calls it in V1, as with
    `revoke_bootstrap_token`), so enrollment — a real tenant-scoped account on a
    real class roster (V0-021) — is the whole join authorization story in V0.
    `PinnedSceneSource` then serves that session's pinned slides through the
    package manifest with a digest check per file, so the student page's content is
    both frozen at start and tamper-evident.
  - **Deliberately not here.** No scheduler (`scheduled_for` is recorded, never
    enforced; `DEC-TECH-003` is `OPEN`), no ordered per-class log or outbox (`DEC-DATA-003`
    is `OPEN` and V1-002 owns it, so a start records state/snapshot/telemetry instead),
    no room/SFU work, and no automatic end — ending is the teacher's explicit `END`
    (V0-010/V0-027). `DEGRADED`/`RECOVERING`/`ENDING` are named in the vocabulary and
    the schema `CHECK` but are not written by V0; `COMPLETED` and `FAILED` are terminal
    (`COMPLETED` except for the explicit `REOPEN`).
  - Durable state: `classes`, `enrollments`, `runtime_session_plans`,
    `classroom_sessions`, `session_snapshots` and `bootstrap_tokens` in
    `app/db/schema.sql` (PostgreSQL reference
    `database/migrations/0004_class_and_session_plan.sql`).
    `app/classroom/telemetry.py` emits `class.scheduled`, `class.started`
    (with `created`), `class.start_blocked` (with `stage` and `issue_code`),
    `class.join`, `class.snapshot_read` and the snapshot failure with identities and
    counts only — never the class title, slide text or notes. Covered by
    `tests/test_class_start.py` (22): the pinned tuple, no-latest-lookup, restart
    survival, the four required failures, concurrency, snapshots, catalog injection,
    token digest/expiry/revocation/epoch, tenancy and telemetry.
- **In-process Classroom Aggregate (V0-010).** `app/classroom/aggregate.py` is the
  single deterministic reducer (`ClassroomAggregate` + `Command`/`Event`/`CommandResult`)
  behind every classroom mutation; the service's `navigate_scene`/`record_checkpoint`/
  `end_class`/`reopen_class` are its command entry points, and `start_class` runs the aggregate's
  `START` and commits the snapshot it produced (byte-identical to V0-009's initial
  snapshot — `snapshot.py::initial_snapshot` was removed in favour of the reducer).
  - **One owner, one reducer.** The service caches one aggregate per class behind a
    per-class lock (`DEC-RUNTIME-001`); the durable store stays the truth.
  - **Idempotency first** (`DEC-RUNTIME-003`): a repeated `command_id` returns its
    stored terminal verdict (accepted *or* refused) and writes nothing; a duplicate
    never reaches the commit point, so exactly one snapshot exists per `state_version`.
  - **Epoch and version fence stale commands** (`DEC-RUNTIME-007`): a command naming a
    stale `expected_actor_epoch`/`expected_state_version` is refused (`STALE_EPOCH`/
    `STALE_STATE_VERSION`) with no effect; the commit's guarded
    `UPDATE … WHERE state = ? AND state_version = ? AND actor_epoch = ?` is the durable
    fence for a writer that lost a race (it reloads and re-handles, bounded).
  - **`END` closes the occurrence.** `ACTIVE/DEGRADED → COMPLETED` (`ENDING`
    in-process only, never persisted), records a final checkpoint, and revokes the
    session's live join tokens so an ended class leaks no credential (`CLASS_END`).
    A completed session's participant content reads are refused `CLASS_ENDED`, while
    its class metadata stays readable; a `START` on it is refused `WRONG_STATE`
    instead of silently returning the ended session (V0-027).
  - **`REOPEN` re-runs the same occurrence** (V0-027). `COMPLETED → ACTIVE` keeps the
    roster and pinned tuple, returns the lesson to its first position, and bumps
    `actor_epoch` before emitting `classroom.session.reopened`; the commit fence uses
    the **pre-command** epoch and writes the new one, so a late command from the old
    epoch cannot land (`DEC-RUNTIME-007`). The service also revokes the session's
    tokens, and `verify_bootstrap_token` refuses a token whose session is no longer
    running as a structural backstop. `FAILED` is not reopened: it requires a new
    class occurrence.
  - **Snapshot round-trip is the recovery story** (`DEC-RUNTIME-004`): `restore`
    validates schema version + checksum before use, so a restart restores the pinned
    tuple and scene position from the newest snapshot and the next command continues
    from that `state_version`; a corrupted snapshot is refused, never replayed.
  - **Deliberately not here.** No broker or actor framework (`DEC-TECH-001/002` stay
    `OPEN`); durable cross-restart dedup and the ordered per-class event log/outbox are
    `DEC-DATA-003` and V1-002. The durable snapshot stays `runtime-snapshot@1` (V0-009's
    contracted shape); the V1 wire envelope (`contracts/snapshots/classroom-snapshot.schema.json`)
    and the command/event wire schemas are V1-002's. V0-027 adds the `end`/`reopen`
    HTTP commands over the same aggregate. Covered by
    `tests/classroom/test_aggregate.py` (16 reducer tests),
    `tests/classroom/test_classroom_commands.py` (8 integration tests) and the
    end/lock/reopen end-to-end test in
    `tests/test_teacher_assigns_and_student_joins.py`.
- **Neutral voice provider (V0-012) is not a decided technology.** `DEC-TECH-007`
  ("TTS/OmniVoice deployment and GPU capacity") is `OPEN`, so
  `docs/adr/proposed/ADR-P007_TTS_OMNIVOICE.md` applies: *"Until accepted,
  provider-neutral interfaces and mocks are used."* `app/speech/` therefore defines
  the domain — the `SpeechProvider` port, the models, the `SpeechService`, the
  classified errors, telemetry and a scripted test double — and
  `app/providers/deterministic.py` is the one local adapter behind it. Nothing here
  is ever reported as a vendor provider.
  - **The domain imports nothing outside itself and the stdlib.**
    `tests/speech/test_layering.py` parses the import graph of `app/speech/` and
    fails if it ever reaches `app.providers` (or any other `app` package or web
    framework), so no provider SDK or vendor error can leak into the classroom
    domain; the adapter depends on the port, never the reverse.
  - **The port base owns the universal transition contract**, so no adapter can
    skip it: admission control (capacity is reserved before use), the end-to-end
    deadline (an injected clock), cooperative cancellation, idempotent cancel ACKs,
    bounded retry, per-generation terminal verdicts, usage and the circuit breaker.
    An adapter implements only `authorize_voice`, `_reserve`, `_release` and
    `_stream`.
  - **A generation is the idempotency key** (`DEC-RUNTIME-003`): a replayed
    synthesis returns its stored terminal verdict without re-running the stream, and
    a replayed `cancel(generation)` returns the stored acknowledgement with
    `duplicate: true` and produces no second side effect.
  - **A timeout never blocks the lesson.** The `SpeechBudget` deadline is checked
    before and between chunks; an overrun is `SYNTHESIS_TIMEOUT`, and
    `SpeechService.speak` returns the **text fallback** (the utterance with its
    semantic markers preserved) rather than waiting. The deadline is cooperative —
    a provider that blocks inside its own stream cannot be preempted in-process;
    the V1 media gateway owns hard timeouts and bounded per-provider queues.
  - **Retry is bounded, classification-driven, and only before any audio emitted.**
    Only `SYNTHESIS_TIMEOUT`/`PROVIDER_UNAVAILABLE` are retried, at most
    `max_attempts`, never past the deadline, and never once a chunk has left the
    attempt (a partial stream cannot be un-emitted, so it fails and the caller
    starts a new generation).
  - **Markers are semantic** (`DEC-RUNTIME-006`): a `MarkerPlan` indexes character
    positions in the **normalized** text, and the millisecond realization the
    provider returns is derived output, not the source of truth.
  - **Failure routes neutral voice, then text** (`DEC-TURN-009`): a refused voice
    re-routes once to the neutral voice, and a timeout/provider error returns the
    text fallback; the reservation is released on every terminal path (best effort,
    never masking the outcome).
  - **Deterministic by construction.** The adapter's audio for a piece of text is a
    pure function of `(voice, language, text)` — sha256-seeded PCM frames — so a
    retry, a re-run or a restarted process is byte-identical and no host sound card
    or installed voice can change it. It doubles as the deterministic mock and the
    local-stack mock (`dev/mocks/tts_mock.py`). Covered by
    `tests/speech/{test_provider_contract,test_speech_service,test_layering}.py`
    (37 tests; backend suite 463 passed). No HTTP route is added: the classroom
    actor/orchestrator is the transport (V0-013/V1).
