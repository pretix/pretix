# Phase 1 ? Verify your clone, pin and boot

[Next phase](02-seed-reset-and-test-planning.md)

Run the assignment from native Windows PowerShell. The team uses the Orders module in the tawassulAkbr/pretix fork. [Course brief](SQE_Final_Project%20Fall%202026.pdf) ? [Windows handoff](../../sqe/handoff.md)

**Evidence.** Baseline and fork verification, installed tool versions, Django system checks, control login, static asset response, authenticated order read and persistence after restart.

## Verify Git and Windows prerequisites

Tawassul coordinates registration in the section's shared sheet and records the actual registration status. Verify that origin points to upstream and team points to the fork. Record the upstream baseline separately from the current working commit. Use the fork's master branch for integration once teammate access is confirmed. [Team ownership and handoffs](#execution-and-handoff-convention)

~~~powershell
Set-Location D:\pretix
git status --short --branch
git remote -v
git rev-parse HEAD
& D:\Python\python.exe --version
node --version
npm.cmd --version
~~~

## Build and smoke-test pretix

1. Create the native Windows virtual environment, install the project dependencies and build the Vite assets using the handoff. Run the Django system check.
2. Initialize the dedicated SQLite instance with the Phase 2 reset command. Start the development app using the Windows serve command. Open http://127.0.0.1:18081/control/login and verify the synthetic manager can see the order list.
3. Check a core static asset and a scoped API GET. Restart the Windows app without resetting the database and repeat the same read. Record the tested commit, runtime versions, HTTP responses, synthetic order code and persisted status. [Reproduction commands and results](../../sqe/handoff.md)

## Selected module and scope

Use the Orders module at baseline `526a79c7d175a37421242a8167821373c357773d`. Record the upstream URL and the AGPLv3 licence with additional terms. [Upstream repository](https://github.com/pretix/pretix) · [Pinned source](https://github.com/pretix/pretix/tree/526a79c7d175a37421242a8167821373c357773d) · [Pinned licence](../../LICENSE)

| Workflow | Starting condition | User action | Expected outcome |
|---|---|---|---|
| W1 Record a manual payment | Synthetic pending EUR 20.00 order with one active ticket, positive outstanding balance and available quota | Orders Manager opens order detail and records the full payment, or calls the REST payment action | Same order becomes paid; a matching payment is confirmed; no real funds move |
| W2 Cancel an order | The same paid order produced by W1, with an active ticket | Orders Manager cancels it with no fee or retains a fee within order total | No fee produces canceled status. A fully funded retained fee can leave the order paid with the ticket positions canceled and the total reduced to the fee. Stop at the refund prompt if shown; refund execution is outside scope |

**Shared records.** Use the same organizer, event and order code across both workflows. Track Order.status, Order.total, active OrderPositions, confirmed OrderPayments and fees. W1 changes the status and payment balance W2 reads. Use fresh fixtures for individual test cases and one explicit W1 → W2 chain on the same record.

**Roles.** Orders Manager has event.orders:read and event.orders:write. Orders Viewer has event.orders:read. Seed two ordinary users and separate scoped API tokens. Keep bootstrap admin for setup only.

**REST.** Use prefix `/api/v1/organizers/{organizer}/events/{event}/orders/{code}/`. Read with GET on the prefix; POST to `mark_paid/` and `mark_canceled/`. Confirm installed behavior against the pinned source. The control panel uses an order transition view, with status p or c for the relevant task screen. Prefer UI labels for Playwright navigation. [Order API docs](https://docs.pretix.eu/dev/api/resources/orders.html)

| Requirement | Expected result in the proposed fixture |
|---|---|
| PAY-01 | An eligible pending order can be marked paid for its outstanding amount. |
| PAY-02 | An eligible expired order can be marked paid when quota can be reacquired. |
| PAY-03 | A second payment action on an already paid order is rejected without creating another confirmed payment. |
| PAY-04 | Viewer can read the order but cannot mark it paid. |
| CAN-01 | An eligible paid order can be canceled without a fee and shows canceled status. |
| CAN-02 | Retaining a fee within the total on a fully paid order cancels positions and reduces the total to the fee. Verify paid status when the retained amount is covered. |
| CAN-03 | Fee above order total is rejected and persisted order, positions and fees remain consistent. |
| CAN-04 | Cancellation rejects a canceled order or an order with zero active positions, without creating duplicate fee records on replay. |
| CAN-05 | Viewer can read the order but cannot cancel it. |

| Business rule | Source to confirm in Phase 2 | Core oracle |
|---|---|---|
| BR-01 Payment eligibility and status | `api/views/order.py` OrderViewSet and `base/models/orders.py` payment confirmation | Pending or expired may proceed; full confirmed payment leads to paid in the fixture. Test quota rejection and separately check any attempt/audit records. |
| BR-02 Cancellation admission | `base/models/orders.py` Order.cancel_allowed | Eligible state AND at least one active position. MCC uses both truth values of both conditions, then MC/DC pairs. |
| BR-03 Cancellation fee limit | `control/forms/orders.py` CancelForm and `base/services/orders.py` _cancel_order | EUR 19.99 / 20.00 / 20.01 on a EUR 20.00 order. Assert decimal precision and rollback on rejection. Establish treatment of zero, null and negative values separately. |
| BR-04 Cancellation outcome | `base/services/orders.py` _cancel_order | No fee → canceled; retained fee with sufficient net payment → paid; retained fee with insufficient net payment → pending. Use active positions, fee and total to distinguish successful cancellation from ordinary paid/pending. |

Paths in the tables are relative to `src/pretix/`. Validate documentation, code and expected behavior on the pinned runtime. For a mismatch, record the references, fixture and rationale in the test basis, and triage it before changing the oracle. Use synthetic email and a local mail sink or disable notifications. Keep online payment, real refunds, external email, unrelated order features and unrelated modules out of the project.

## Execution and handoff convention

Put course artifacts in `sqe/` and student-authored tests in `src/tests/team/`. Run Django, scoped pytest and Playwright with the native Windows commands in the handoff. The app binds to Windows loopback and the fixture database is separate from other pretix data. Use equivalent Windows and SQLite settings for comparable CI functional runs. [Windows handoff](../../sqe/handoff.md)

Maintain `sqe/handoff.md` and an evidence index. At each phase exit record the baseline and current SHA, commands, results, test and requirement IDs, risk IDs, evidence paths, amendments, pending checks, and next phase inputs. Record passes when the team has run evidence.

| Owner | Branch | Work and browser cases |
| --- | --- | --- |
| Tawassul | `sqe/setup` for the shared base | Setup and fixtures, SonarQube and white-box tests, mutation and CI, the shared Playwright runner, UC-01 and UC-02, final integration and submission. |
| Member 2 | `sqe/api-and-e2e` | OpenAPI, generated data, API and integration tests, UC-03 and UC-04. |
| Member 3 | `sqe/browser-quality` | Usability, accessibility, defensive security, performance and recovery, UC-05 and UC-06. |

Tawassul lands the shared fixtures, Playwright project and initial PR workflow on the fork's integration branch before the teammates open their PRs. Share test management and commit your own changes. Keep prompts and maintain `sqe/ai-use.md` with the tool, purpose, output, and what the student checked or changed. [Playwright phase](05-playwright-use-cases.md) · [Teammate commits](../04-teammate-commits.md) · [Rubric cross-check](09-submission-and-viva.md#rubric-cross-check)

## Phase files

1. [Verify your clone, pin and boot](01-windows-setup.md)
2. [Seed/reset, test basis and management](02-seed-reset-and-test-planning.md)
3. [Static analysis, CFG and white-box tests](03-static-analysis-and-unit-tests.md)
4. [OpenAPI, generated data and API/integration tests](04-openapi-and-api-tests.md)
5. [Playwright end-to-end and use cases](05-playwright-use-cases.md)
6. [Automated usability, accessibility and defensive checks](06-usability-accessibility-and-security.md)
7. [Performance and recovery](07-performance-and-recovery.md)
8. [Mutation, GitHub Actions and PR evidence](08-mutation-and-ci.md)
9. [Clean-run E2E, final evidence and submission](09-submission-and-viva.md)
