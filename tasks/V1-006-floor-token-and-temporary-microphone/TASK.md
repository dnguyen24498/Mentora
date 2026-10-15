# V1-006: Floor token and temporary microphone

**Week:** W11  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Replace fake floor publication with real fenced media authorization.

## Dependencies

- V1-004
- V1-005

## Requirement IDs

- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-TURN-008`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `contracts/security/floor-token-claims.schema.json`
- `contracts/events/floor-granted.schema.json`
- `docs/sequences/MIC_PUBLISH_FAILURE.md`

## In Scope

- Mint short-lived floor token.
- Independent media-side claim/epoch/revocation validation.
- Browser mic permission only after floor.
- Track publication ACK.
- Expiry/revoke/unpublish.

## Out of Scope

- STT transcription.
- Discussion mode.

## Acceptance Criteria

- Wrong/expired/stale-epoch/replayed token rejected.
- UI never shows active transmission before track ACK.
- Publish failure releases floor.

## Required Tests

- Token negatives, mic denial, publish timeout, duplicate callback, failover epoch.

## Files/Areas Allowed to Change

- `backend/app/media/`
- `backend/app/security/`
- `frontend/apps/classroom/`
- `tests/security/`
- `tests/e2e/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
