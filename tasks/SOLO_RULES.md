# Solo Development Rules

1. WIP limit is one implementation task.
2. Keep each diff reviewable in 30–90 minutes; split tasks if necessary.
3. Never replace a mock and change domain behavior in the same task.
4. Do not add infrastructure to avoid writing a small deterministic module.
5. Deploy the golden path every week.
6. Reserve one half-day per week for tests, cleanup, specs, and cost review.
7. If two consecutive days pass without a working demo, reduce scope.
8. Cut optional scope before weakening versioning, isolation, idempotency, grounding, or recovery.
