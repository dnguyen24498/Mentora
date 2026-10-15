# Mentora Engineering Specification

This is the single reconciled specification set for Mentora. It supersedes every previously generated ZIP or document set.

## Start here

1. `SOURCE_OF_TRUTH.md`
2. `docs/architecture/00_ARCHITECTURE_BASELINE.md`
3. `docs/architecture/01_OVERALL_ARCHITECTURE.md`
4. `docs/architecture/ARCHITECTURE_FULL.md`
5. `governance/DECISION_LEDGER.yaml`
6. `governance/TERMINOLOGY_REGISTRY.yaml`
7. `governance/TRACEABILITY_MATRIX.csv`
8. `AI_IMPLEMENTATION_GUIDE.md`

## Consistency model

- Architecture files define stable responsibilities and invariants.
- Decision ledger records what is LOCKED, PROPOSED, or OPEN.
- ADRs under `docs/adr/proposed/` are not accepted decisions.
- Machine-readable contracts implement architecture requirement IDs.
- Every detailed specification contains requirement IDs or references to canonical files.
- `CONSISTENCY_REPORT.md` identifies coverage, unresolved choices, and validation results.

Do not combine this package with older generated packages. Older packages are obsolete.
