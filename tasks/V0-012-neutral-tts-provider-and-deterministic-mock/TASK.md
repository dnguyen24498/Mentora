# V0-012: Neutral TTS provider and deterministic mock

**Week:** W6  
**Status:** TODO  
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

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
