# V0-015: Grounded text question

**Week:** W7  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Answer typed questions from pinned evidence and resume lesson.

## Dependencies

- V0-013
- V0-014

## Requirement IDs

- `DEC-DATA-005`
- `DEC-RUNTIME-002`
- `DEC-RELIABILITY-001`
- `DEC-TURN-009`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/14_LLM_RAG_AND_AI_SAFETY.md`
- `docs/providers/LLM_PROVIDER.md`
- `contracts/commands/text-question.schema.json`
- `docs/sequences/RAG_OR_LLM_TIMEOUT.md`

## In Scope

- Submit text command.
- Save/pause checkpoint.
- Authorized pinned retrieval.
- Structured grounded answer with evidence IDs and insufficient-evidence result.
- Optional answer TTS and resume.

## Out of Scope

- Free-form agent tools.
- General web search.
- Official grading.

## Acceptance Criteria

- Cross-tenant/course/version retrieval is zero.
- No fabricated evidence ID.
- Timeout/defer resumes safely.

## Required Tests

- Grounded, insufficient evidence, provider timeout, cancellation, duplicate question, isolation tests.

## Files/Areas Allowed to Change

- `backend/app/questions/`
- `backend/app/knowledge/`
- `backend/app/llm/`
- `frontend/apps/classroom/`
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
