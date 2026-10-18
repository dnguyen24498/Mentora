# V0-012: Neutral TTS provider and deterministic mock

**Week:** W6  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Add provider-neutral neutral voice with deadline, cancellation, metrics, and mock.

## Dependencies

- FND-002
- V0-010

## Requirement IDs

- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/providers/TTS_VOICE_PROVIDER.md`
- `docs/state-machines/TEACHER_VOICE_STATE_MACHINE.md`

## In Scope

- Domain interface.
- Deterministic mock.
- One accepted neutral provider adapter.
- Reservation/stream/cancel/release/health/usage.
- Text fallback.

## Out of Scope

- Cloned voice.
- GPU scheduler.
- Multiple production providers.

## Acceptance Criteria

- Provider timeout does not block lesson indefinitely.
- Cancellation is idempotent.
- Provider SDK does not leak into classroom domain.

## Required Tests

- Mock contract, timeout, cancel twice, provider error, fallback.

## Files/Areas Allowed to Change

- `backend/app/speech/`
- `backend/app/providers/`
- `dev/mocks/`
- `tests/contract/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR: `TBD` (see `STATUS.yaml` for the recorded hash)
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest tests/speech -q` — **37 passed**; full suite `env -u PYTHONPATH .venv/bin/python -m pytest -q` — **463 passed** (was 426; +37)
- Demo recording/screenshot: `python3 dev/mocks/tts_mock.py --text "Hello class, welcome to the lesson." --marker 0:start --marker 12:welcome --out /tmp/tts.wav` — prints the classified outcome as JSON and writes a playable deterministic WAV (verified with the stdlib `wave` module: 1 channel, 8000 Hz, 16-bit)
- Metrics observed: `SpeechTelemetry` counters (`reservations_granted/denied/released`, `generations_started/completed/failed/cancelled`, `cancel_acks/replays`, `retries`, `timeouts`, `voice_fallbacks`, `text_fallbacks`, `characters_synthesized`, `audio_ms_total`) plus structured events (`speech.reserved/reservation_denied/released/segment/cancel/voice_fallback/text_fallback/outcome/health`) — identities, counts and sizes only, **never** the spoken text.
- Traceability rows added: `DEC-RELIABILITY-001`, `DEC-RUNTIME-003`, `DEC-RUNTIME-006`, `DEC-TURN-009`, `DEC-DEPLOY-002`.
- Known limitations:

## Files/Areas Allowed to Change (as delivered)

- `backend/app/speech/` -> created: `models.py`, `errors.py`, `port.py`,
  `service.py`, `telemetry.py`, `testing.py`, `__init__.py`. The **domain**:
  the `SpeechProvider` port, the models, the `SpeechService`, the classified
  errors, structured telemetry and the scripted test double. It imports nothing
  outside itself and the stdlib.
- `backend/app/providers/` -> created: `deterministic.py` (the one neutral
  adapter / deterministic mock), `factory.py` (`create_speech_provider`,
  `build_speech_service`), `__init__.py`. The **adapter** side.
- `dev/mocks/` -> created: `tts_mock.py` (the runnable local-stack mock TTS) and
  `README.md`.
- `tests/contract/` -> `backend/tests/speech/` (the only test root `pytest`
  collects — `testpaths = ["tests"]` is relative to `backend/`; the same mapping
  precedent as V0-010/V0-011). Added `test_provider_contract.py`,
  `test_speech_service.py`, `test_layering.py`, `helpers.py`, `__init__.py`.

Also touched (required to keep the tree consistent):
`docs/architecture/13_MEDIA_SPEECH_AND_VOICE.md` + regenerated
`docs/architecture/ARCHITECTURE_FULL.md`, `governance/TRACEABILITY_MATRIX.csv`,
`tasks/STATUS_BOARD.csv`, `AGENTS.md`, `backend/README.md`, this task folder.

## What was delivered

A **provider-neutral neutral voice** behind a domain port, plus the one
deterministic adapter V0 runs with (V0-012):

- **Domain port** (`app/speech/port.py`): `SpeechProvider` with
  `authorize_voice`, `reserve`, `synthesize` (streaming via an `on_chunk` sink),
  `cancel`, `release`, `health`/`identity`. The base owns the *universal
  transition contract* every adapter must honour, so no adapter can skip it:
  admission control, the end-to-end deadline, cooperative cancellation,
  idempotent cancel ACKs, bounded retry, per-generation terminal verdicts, usage
  and circuit-breaker state. An adapter implements only `authorize_voice`,
  `_reserve`, `_release` and `_stream`.
- **Deterministic mock/adapter** (`app/providers/deterministic.py`):
  `neutral-deterministic@1.0.0`. The audio for a piece of text is a pure function
  of `(voice, language, text)` — sha256-seeded PCM frames — so a retry, a re-run
  or a restarted process is byte-identical. No network, no credentials, no GPU.
  It doubles as the deterministic mock and the dev-stack mock.
- **Reserve/stream/cancel/release/health/usage**: capacity is reserved before
  use and released on every terminal path (best effort, never masking the
  outcome); `health()` reports circuit state, in-flight, capacity and counters;
  `usage()` aggregates characters/audio/cost/region.
- **Text fallback** (`app/speech/service.py`): `SpeechService.speak` never raises
  — it returns `COMPLETED` (audio) / `CANCELLED` / `FALLBACK` (the utterance as
  text, with its semantic markers preserved, so captions and the timeline can
  still sync). A refused voice first re-routes to the neutral voice, then text.
- **Timeout does not block the lesson**: an injected-clock `SpeechBudget` turns
  an overrun into `SYNTHESIS_TIMEOUT` between chunks, and the service returns the
  text fallback instead of waiting.
- **Idempotent cancellation**: `cancel(generation)` sets the in-flight token
  once; a replay returns the stored ACK with `duplicate=true` and produces no
  second side effect.
- **No SDK leak**: `app/speech/` imports nothing outside itself and the stdlib;
  `test_layering.py` parses the import graph and fails if it ever does. The
  adapter depends on the port, never the reverse.

## Known limitations

- **The provider is not decided.** `DEC-TECH-007` (TTS/OmniVoice deployment and
  GPU capacity) is `OPEN`; per `ADR-P007` this ships the interface plus a mock and
  reports `neutral-deterministic@1.0.0`, never a vendor provider. Wiring a real
  provider is a later adapter + an accepted decision, not a domain change.
- **The deadline is cooperative.** It is enforced between chunks (and before the
  attempt), so a provider that *blocks* inside its own stream cannot be preempted
  in-process; the V1 media gateway owns hard timeouts and bounded per-provider
  queues. The acceptance criterion — *a provider timeout does not block the lesson
  indefinitely* — holds because the failure is classified and the lesson continues
  on text.
- **Synchronous, in-process.** `SpeechService.speak` is a blocking call with no
  queue; per-tenant/provider bounded queues, real queue-depth metrics and
  backpressure belong to the job/gateway layer (the same place the renderer's
  admission control is deferred to).
- **Cloned voice is out of scope.** `VoiceKind` has one member; a non-neutral
  voice is refused by `authorize_voice` and routed to the neutral voice. Consent/
  scope/expiry/revocation/deletion/audit is V1.
- **Audio is a deterministic stand-in.** The frames are a sha256-seeded signal,
  not speech; they exist so streaming, duration, markers and bytes are exercised
  deterministically. Nothing in the platform renders them to a listener yet
  (playback/timeline is V0-013).
- **No HTTP endpoint (by design).** The task's allowlist has no API area; the
  classroom actor/orchestrator is the transport (V0-013/V1) and the dev stack
  reaches it through `dev/mocks/tts_mock.py`.
- **`FND-002` remains `TODO`.** Per the owner's decision, the deterministic
  adapter is treated as V0's explicitly-approved temporary mock (FND-002's
  acceptance criterion allows "an accepted ADR **or explicitly approved temporary
  mock**"); the ADRs are not accepted and `DEC-TECH-007` stays `OPEN`. `FND-001`
  (repo bootstrap, CI/lint) is likewise still `TODO`; quality still relies on
  `pytest`/`tsc` run manually.
