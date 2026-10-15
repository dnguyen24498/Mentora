# V0-002: Secure PPTX upload

**Week:** W2  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Implement immutable tenant-authorized PPTX upload and compiler-job creation.

## Dependencies

- V0-001

## Requirement IDs

- `DEC-CONTENT-001`
- `DEC-CONTENT-005`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/04_CONTENT_COMPILER.md`
- `docs/security/THREAT_MODEL_AND_CONTROLS.md`
- `docs/sequences/COURSE_UPLOAD_PUBLICATION.md`

## In Scope

- Upload endpoint.
- Authorization and tenant/course scope.
- Streaming size limit, filename normalization, extension, MIME/magic validation, SHA-256, scanner adapter.
- Immutable object key and source artifact/job transaction.
- Idempotent duplicate upload behavior.

## Out of Scope

- PPTX extraction.
- Rendering.
- Publication.

## Acceptance Criteria

- Valid PPTX creates one source artifact and one job.
- Invalid/oversized/spoofed files are rejected with stable error codes.
- Retry does not duplicate artifact or job.
- Partial failure leaves no visible corrupt artifact.

## Required Tests

- Valid, duplicate, oversized, wrong magic, cross-tenant, storage timeout, interrupted upload.

## Files/Areas Allowed to Change

- `backend/app/courses/`
- `backend/app/storage/`
- `backend/app/security/`
- `contracts/openapi/`
- `database/`
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
