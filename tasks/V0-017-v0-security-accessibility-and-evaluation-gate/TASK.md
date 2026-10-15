# V0-017: V0 security accessibility and evaluation gate

**Week:** W8  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make V0 safe enough for controlled internal demo.

## Dependencies

- V0-016

## Requirement IDs

- `DEC-CONTENT-006`
- `DEC-DATA-005`
- `DEC-TURN-009`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/security/THREAT_MODEL_AND_CONTROLS.md`
- `docs/accessibility/CLASSROOM_ACCESSIBILITY.md`
- `docs/testing/CONTENT_AND_AI_EVALUATION.md`

## In Scope

- Tenant negative tests.
- Upload abuse tests.
- Prompt-injection fixtures.
- Keyboard/caption/focus/contrast checks.
- 20-PPTX and grounded-question evaluation report.
- Cost and latency report.

## Out of Scope

- Penetration-test certification.
- Broad browser matrix.

## Acceptance Criteria

- No critical isolation issue.
- No blocking accessibility issue in golden path.
- Known fidelity limitations documented.

## Required Tests

- Security, accessibility, compiler corpus, RAG evaluation.

## Files/Areas Allowed to Change

- `tests/security/`
- `tests/accessibility/`
- `evaluation/`
- `CONSISTENCY_REPORT.md`
- `README.md`

## Quality Gate

V0 release candidate is demoable from a fresh environment with documented limits.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
