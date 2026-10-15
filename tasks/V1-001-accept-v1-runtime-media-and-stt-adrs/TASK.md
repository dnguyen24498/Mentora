# V1-001: Accept V1 runtime media and STT ADRs

**Week:** W9  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Choose only the implementations necessary for V1 pilot.

## Dependencies

- V0-017

## Requirement IDs

- `DEC-DATA-003`
- `DEC-TURN-006`
- `DEC-DEPLOY-002`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/adr/proposed/ADR-P001_ORDERED_STREAM.md`
- `docs/adr/proposed/ADR-P002_ACTOR_RUNTIME.md`
- `docs/adr/proposed/ADR-P004_SFU.md`
- `docs/adr/proposed/ADR-P006_STT.md`

## In Scope

- Prototype/benchmark ordered ownership, actor fencing, managed SFU/TURN, Vietnamese STT.
- Accept decisions or explicitly choose a staged Level-2 design.
- Update ledger and rollout/rollback.

## Out of Scope

- Multi-region active-active.
- Self-hosted voice cloning.

## Acceptance Criteria

- Every V1 pilot dependency has accepted decision and measured evidence.

## Required Tests

- ADR consistency checks.

## Files/Areas Allowed to Change

- `docs/adr/`
- `governance/`
- `evaluation/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
