# FND-001: Repository bootstrap and quality commands

**Week:** W1  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create a reproducible local and CI skeleton before business logic.

## Dependencies

- None

## Requirement IDs

- `DEC-DEPLOY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/24_ROADMAP_AND_REPOSITORY.md`

## In Scope

- Create backend, frontend, compiler, workers, tests, scripts directories.
- Create one-command local startup and one-command quality check.
- Add health endpoints/pages.
- Add formatting, linting, typing, unit-test, schema, OpenAPI, migration, and spec-consistency jobs.

## Out of Scope

- Business features.
- Realtime media.
- Cloud production deployment.

## Acceptance Criteria

- Fresh clone starts locally with documented commands.
- CI fails on invalid schema, migration, or generated architecture drift.
- No production secret is committed.

## Required Tests

- CI smoke test.
- Empty-database migration apply.
- JSON Schema and OpenAPI validation.

## Files/Areas Allowed to Change

- `backend/`
- `frontend/`
- `compiler/`
- `workers/`
- `tests/`
- `scripts/`
- `dev/`
- `infra/`
- `.github/ or CI config`
- `README.md`

## Quality Gate

A clean clone reaches green CI in less than 15 minutes.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
