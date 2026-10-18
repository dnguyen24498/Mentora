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
