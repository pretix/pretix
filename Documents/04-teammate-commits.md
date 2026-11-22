# Pretix SQE teammate commits

Member 2 and Member 3 each commit their own changes on their own branch in `tawassulAkbr/pretix` using Git author details linked to their GitHub account. Each row gives a suggested commit and message. [Assignment §§2 and 6](Phases/SQE_Final_Project%20Fall%202026.pdf)

## Member 2

Suggested branch `sqe/api-and-e2e`. [API implementation](Phases/04-openapi-and-api-tests.md) · [UC-03 and UC-04](Phases/05-playwright-use-cases.md#teammate-use-cases)

| What to commit | Suggested commit message |
| --- | --- |
| OpenAPI spec or pinned spec reference for the scoped Orders endpoints, the EP and three-point BVA generator, and the output or run instructions for two changed constraints. | `feat(sqe): generate Orders API test data from OpenAPI` |
| API tests that consume the generated data and check payment, cancellation, rejected inputs, and persisted outcomes. Put the tests under `src/tests/team/api/` and link their requirement IDs. | `test(sqe): cover Orders API rules and persisted outcomes` |
| UC-03 and UC-04 specifications under `sqe/use-cases/` and their Playwright specs under `src/tests/team/e2e/`. Include the local test command and link actual run evidence. | `test(e2e): cover retained fees and payment-to-cancellation flows` |

## Member 3

Suggested branch `sqe/browser-quality`. [UC-05 and UC-06](Phases/05-playwright-use-cases.md#teammate-use-cases) · [Browser quality and defensive checks](Phases/06-usability-accessibility-and-security.md) · [Performance and recovery](Phases/07-performance-and-recovery.md)

| What to commit | Suggested commit message |
| --- | --- |
| UC-05 and UC-06 specifications under `sqe/use-cases/` and their Playwright specs under `src/tests/team/e2e/`. Include the local test command and link actual run evidence. | `test(e2e): cover exceptional payments and keyboard cancellation` |
| Playwright accessibility and role checks, screen fix, and a summary with the actual Lighthouse and axe before/after reports. Include the manager and viewer access matrix. | `test(sqe): verify Orders accessibility and role permissions` |
| Defensive assessment notes and evidence links, plus the k6 script, observed performance results, and automated recovery check for the local synthetic test instance. | `test(sqe): measure Orders performance and verify recovery` |

## Before opening your PR

1. Start from the team fork's planned integration branch, `master`, once the shared Playwright configuration and fixture commands are available. Open the PR against that branch in `tawassulAkbr/pretix`.
2. Run your tests against reset synthetic data. In the PR, list the case IDs, the command you ran, the observed result, and links to the evidence. [Playwright run instructions](Phases/05-playwright-use-cases.md#run-on-windows-and-record-evidence)
3. Stage your own changed files and review `git diff --cached` before committing. Keep credentials, session state, and raw responses with secrets out of Git.
