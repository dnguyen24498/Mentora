# V1-008: Voice question answer and semantic resume

**Week:** W12  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Connect final transcript to pinned answer and safe classroom resume.

## Dependencies

- V1-007
- V0-015

## Requirement IDs

- `DEC-RUNTIME-005`
- `DEC-DATA-005`
- `DEC-TURN-007`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`
- `docs/sequences/RAISE_HAND_SUCCESS.md`
- `docs/sequences/RAG_OR_LLM_TIMEOUT.md`

## In Scope

- Final transcript to question.
- Pinned retrieval and grounded response.
- New answer audio generation.
- Understanding check.
- Restore compatible checkpoint and continue.

## Out of Scope

- Advanced personalization.
- Teacher voice cloning.

## Acceptance Criteria

- No old audio generation resumes.
- Timeout/defer preserves class.
- Citations match pinned index.

## Required Tests

- Success, insufficient evidence, LLM/TTS timeout, actor restart at each boundary.

## Files/Areas Allowed to Change

- `backend/app/questions/`
- `backend/app/classroom/`
- `frontend/apps/classroom/`
- `tests/e2e/`
- `tests/chaos/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
