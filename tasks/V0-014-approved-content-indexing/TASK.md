# V0-014: Approved-content indexing

**Week:** W7  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Index published content with mandatory metadata and rebuildability.

## Dependencies

- V0-008
- FND-002

## Requirement IDs

- `DEC-DATA-005`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/providers/SEARCH_PROVIDER.md`
- `docs/architecture/14_LLM_RAG_AND_AI_SAFETY.md`

## In Scope

- Chunk approved scripts/text/notes.
- Attach tenant/course/version/package/index/scene/source metadata.
- Build/rebuild/delete version.
- Search adapter and deterministic mock.

## Out of Scope

- Unreviewed Teaching Graph.
- Personal memory.

## Acceptance Criteria

- Index is invisible until complete.
- Filter fields are mandatory.
- Rebuild reproduces compatible logical index.

## Required Tests

- Missing metadata, rebuild, wrong version, cross-tenant negative tests.

## Files/Areas Allowed to Change

- `backend/app/knowledge/`
- `workers/indexing/`
- `evaluation/`
- `tests/integration/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
