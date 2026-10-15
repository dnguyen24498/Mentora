# V0-007: Teacher review preview

**Week:** W4  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create a minimal review UI for render, text, notes, warnings, and lesson order.

## Dependencies

- V0-006

## Requirement IDs

- `DEC-CONTENT-006`
- `DEC-CONTENT-008`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/07_PUBLICATION_AND_REVIEW.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`

## In Scope

- Teacher Studio course-version page.
- Side-by-side rendered scene and extracted information.
- Warnings/fidelity and blocking status.
- Approve/reject and simple scene-order/script edits.

## Out of Scope

- Graph editor.
- Multi-review workflow.
- Advanced policy editor.

## Acceptance Criteria

- Teacher cannot approve blocking failures.
- Edits create draft data, not mutate published package.
- Keyboard and basic screen-reader operation.

## Required Tests

- UI component tests.
- Authorization tests.
- Blocking-warning E2E.

## Files/Areas Allowed to Change

- `frontend/apps/teacher-studio/`
- `backend/app/publication/`
- `backend/app/courses/`
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
