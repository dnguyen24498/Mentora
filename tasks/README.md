# Mentora Task Execution System

This backlog is optimized for one developer using AI assistance. Execute tasks in dependency order, not by asking AI to implement a whole phase.

## Daily workflow

1. Pick one unblocked task from `STATUS_BOARD.csv`.
2. Open the task folder and read `TASK.md`.
3. Give `PROMPT.md` to the coding agent.
4. Review the analysis before allowing code.
5. Keep the diff within task scope.
6. Run required tests and quality gate.
7. Fill Completion Evidence and update `STATUS.yaml`.
8. Update traceability and commit.

## Hard rule

Only one task may be `IN_PROGRESS` at a time for a solo developer. WIP limit = 1.

## Critical path

```text
FND-001 -> FND-002/FND-003
-> V0-001..V0-017
-> V1-001..V1-010
```

## Release milestones

- End W4: content upload, compilation, review, publication.
- End W7: single-student teaching plus grounded text Q&A.
- End W8: V0 release candidate.
- End W10: Raise Hand state machine proven with mocks.
- End W11: real SFU, microphone, and STT.
- End W12: controlled V1 pilot gate.
