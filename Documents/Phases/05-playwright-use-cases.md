# Phase 5 — Playwright end-to-end and use cases

[Phase list](01-windows-setup.md#phase-files) · [Previous phase](04-openapi-and-api-tests.md) · [Next phase](06-usability-accessibility-and-security.md)

Use the Phase 2 fixture contract, Phase 4 readback, and the RTM to test W1 manual payment and W2 cancellation in the pretix control panel. Run Chromium from PowerShell against the dedicated native Windows test instance on loopback. [Orders scope](01-windows-setup.md#selected-module-and-scope) · [Seed and reset plan](02-seed-reset-and-test-planning.md) · [API readbacks](04-openapi-and-api-tests.md)

Use the shared Playwright project and fixture commands for Tawassul's UC-01 and UC-02. See the handoff for measured results and teammate integration status. [Windows handoff](../../sqe/handoff.md)

| Owner | Use cases | Deliverables |
| --- | --- | --- |
| Tawassul | UC-01 manual payment and UC-02 no-fee cancellation | Shared Playwright project, fixture helpers, own cases, and integrated run. |
| Member 2 | UC-03 retained fee and UC-04 pay then cancel the same order | Own Playwright specs and the same-order readbacks after W1 and W2. [Commit instructions](../04-teammate-commits.md#member-2) |
| Member 3 | UC-05 exceptional payments and UC-06 keyboard cancellation | Own Playwright specs and a handoff of the keyboard and fee-correction flows to Phase 6. [Commit instructions](../04-teammate-commits.md#member-3) |

## Prepare the shared runner

1. Start the dedicated app with its test database and volume. Use an English-language EUR event with a EUR 20.00 item. Seed manager and viewer accounts and named pending, paid, expired-with-quota, expired-without-quota, canceled, and positionless orders. Use fresh synthetic records for each flow. Record the exact start, seed and reset commands and fixture aliases in `sqe/handoff.md` for each author and CI.
2. Tawassul puts the Chromium configuration, `package.json`, lockfile, fixture helpers, and local setup instructions on the shared base. Use `src/tests/team/e2e/` for the Playwright project and `sqe/use-cases/` for specifications. Read the app URL, organizer and event slugs, credentials and read token from local configuration. Use separate browser contexts per role, one worker when cases share a fixture database, and an HTML report with traces on failure.
3. Each author verifies the candidate flows against the pinned runtime, then records each flow's actor, preconditions, steps, visible result and persisted postcondition. Automate the main flow, at least two alternatives and at least two exceptions for every case. If a flow is unreachable, document a reachable replacement in the same workflow. Use case IDs in test titles and map requirements and risks in the RTM. Count a shared execution once when its fixture, action and assertions are the same.

Use role and label locators and Playwright's waiting assertions. Turn off customer email in the forms and end at any refund prompt. Re-read the order through authenticated `GET /api/v1/organizers/{organizer}/events/{event}/orders/{code}/` or read-only fixture inspection. No-fee cancellation sets the canceled status and date and preserves the total, position rows and their existing `canceled` flags. A nonzero retained fee cancels the positions, adds the fee, reduces the total, and leaves the order paid or pending according to the net confirmed payment. Use an order without unrelated fees or prior refunds for the basic assertions. [Payment form](../../src/pretix/control/templates/pretixcontrol/order/pay.html) · [Cancellation form](../../src/pretix/control/templates/pretixcontrol/order/cancel.html) · [Order serializer](../../src/pretix/api/serializers/order.py) · [Cancellation service](../../src/pretix/base/services/orders.py)

## Tawassul's UC-01 and UC-02

| Flow | Action | Visible and persisted checks |
| --- | --- | --- |
| UC-01 main | Manager opens a pending order, selects **Mark as paid**, and submits EUR 20.00 with **Create payment**. | Payment confirmation appears. Order becomes `p`. Exactly one new confirmed manual payment is EUR 20.00 and the ticket position is unchanged. |
| UC-01 alt 1 | Record EUR 20.00 with a valid prior payment date. | Confirmation appears. Read back the confirmed payment and the chosen date in the event timezone. |
| UC-01 alt 2 | Pay an expired order with available quota and late payment enabled. | Confirmation appears. Order becomes `p` with one confirmed payment. |
| UC-01 exc 1 | Enter EUR 20.001 in the payment amount. | The order detail still shows Pending and no success message appears. Stored state is unchanged. The missing field-level error is recorded in the test basis. |
| UC-01 exc 2 | Try to pay an expired order with exhausted quota and leave the force option off. | Rejection appears. Order remains expired with no new confirmed payment. Record any failed payment attempt separately. |
| UC-02 main | Manager opens a paid order, selects **Cancel order**, leaves the fee empty, and selects **Yes, cancel order**. | Cancellation confirmation or refund prompt appears. Order becomes `c` with a cancellation date and zero cancellation fees. The confirmed payment is still present. |
| UC-02 alt 1 | Cancel a pending order with an empty fee. | Cancellation confirmation appears. Order becomes `c` with zero cancellation fees and no new payment. |
| UC-02 alt 2 | Cancel an expired order that still has an eligible position, with an empty fee. | Cancellation confirmation appears. Order becomes `c` with zero cancellation fees. |
| UC-02 exc 1 | Viewer opens an eligible paid order detail page. | The order is readable and the cancellation action is unavailable. A fresh read shows the order, positions, payments, and fees unchanged. |
| UC-02 exc 2 | Manager opens an already-canceled order. | The cancellation action is unavailable. Status, cancellation date, and fee count remain unchanged. |

## Teammate use cases

| Case | Main flow | Alternatives | Exceptions | Persisted checks |
| --- | --- | --- | --- | --- |
| UC-03 Retain a cancellation fee | Cancel a paid order with a fee below the total. | Retain a fee equal to the total. Retain a fee on an unpaid pending order. | Enter a fee above the total. Enter a fee with invalid decimal precision. | Compare status, total, positions and fees after each flow. |
| UC-04 Pay and cancel the same order | Pay a pending order and cancel it with no fee. | Retain a fee on cancellation. Start with an expired order eligible for late payment. | Reject payment when quota is exhausted. Reject a fee after payment. | Read the same order code before payment, after W1 and after W2. Check the confirmed W1 payment and the W2 status, total, positions and fees. |
| UC-05 Handle an exceptional payment | Settle an expired order with available quota. | Make a partial payment and then pay the remaining amount. Reuse a seeded matching manual payment. | Enter an invalid payment date. Open a canceled order and verify payment is unavailable. | Check order status and the number, state and amount of payments. |
| UC-06 Cancel with the keyboard | Tab through the form for a paid order and submit by keyboard. | Enter a zero fee on a pending order. Retain a valid fee. | Submit an above-cap fee and correct it. Open the order as a viewer and verify cancellation is unavailable. | Check order status, total, positions and fees. Verify state after the rejection and again after correction. |

## Run on Windows and record evidence

Each author runs their cases against reset fixtures and commits their own changes. Include IDs, commands, observed results and evidence links in the PR. Tawassul runs all six cases together. If PRs are still open, use a candidate checkout that combines the authored commits and record its SHA. Confirm that the manager can perform both workflows, the viewer can read the order, and both viewer write denials leave the relevant records unchanged. Link the payment task, keyboard submission and fee-correction checks for [Phase 6](06-usability-accessibility-and-security.md).

From the repository root, record `git rev-parse HEAD` and reset the dedicated app. Playwright starts and stops the loopback server and reads the fixture configuration from the ignored local directory.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 reset
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) 'local\sqe\browsers'
Set-Location .\src\tests\team\e2e
npm.cmd ci
npm.cmd exec -- playwright install chromium --only-shell
npm.cmd test
```

| Evidence | What to record |
| --- | --- |
| Build and environment | Tested SHA, image ID, database, seed/reset commands, Windows and Playwright/Chromium versions |
| Suite result | Exact command, case IDs, observed pass/fail/skip counts, HTML report or CI run link, and failure traces |
| Same-order W1 → W2 proof | Synthetic order code, starting state, after-W1 payment and status, and after-W2 status, total, positions and fees |
| Deviations | Blocked or failed checks, issue or PR links, and the result after resetting and rerunning; preserve the original result |

Sanitize shared evidence and update the evidence index and RTM. Use the same procedure for the [Phase 9 clean run](09-submission-and-viva.md).

## Tawassul's E2E commits

| What to commit | Suggested message |
| --- | --- |
| Shared runner, configuration, fixture helpers, and setup instructions | `test(e2e): add shared Playwright runner and Orders fixtures` |
| UC-01 and UC-02 specifications and Playwright tests | `test(e2e): cover manual payments and no-fee cancellations` |
| Clean-run summary and evidence links after any integration fixes | `docs(e2e): record clean Orders suite results` |

**Exit evidence.** Six use cases with every flow automated, an integrated HTML report with run results, and stored-state evidence for the same-order W1 → W2 journey.
