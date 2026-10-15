# V1-009: Moderator and accessible realtime controls

**Week:** W12  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Add minimum pilot moderation and equivalent nonvoice access.

## Dependencies

- V1-003
- V1-007

## Requirement IDs

- `DEC-TURN-009`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/18_ACCESSIBILITY_AND_INCLUSION.md`
- `docs/accessibility/CLASSROOM_ACCESSIBILITY.md`

## In Scope

- Moderator queue view/select/skip/revoke.
- Keyboard Raise/Cancel/Finish.
- Screen-reader queue/floor/mic/recovery announcements.
- Typed question equivalent.
- Audit overrides.

## Out of Scope

- Advanced analytics dashboard.
- Multi-moderator workflow.

## Acceptance Criteria

- All critical realtime controls work keyboard-only.
- Overrides are authorized and audited.

## Required Tests

- Role negatives, keyboard E2E, screen-reader semantics, revoke during speaking.

## Files/Areas Allowed to Change

- `frontend/apps/classroom/`
- `backend/app/classroom/turn/`
- `backend/app/audit/`
- `tests/accessibility/`
- `tests/security/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
