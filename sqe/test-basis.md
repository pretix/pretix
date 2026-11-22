# Orders test basis

Use the seeded EUR 20.00 order in the sqe-orders/orders event. The order code, status, total, positions, payments and fees provide the stored-state checks for both manual payment (W1) and cancellation (W2). The Orders Manager has event.orders:read and event.orders:write. The Orders Viewer has event.orders:read. [Scope and requirement definitions](../Documents/Phases/01-windows-setup.md#selected-module-and-scope)

| Start | W1 manual payment | W2 cancellation |
| --- | --- | --- |
| Pending with active position | Full confirmed payment leads to paid. A partial payment leaves pending. | Empty or zero fee leads to canceled. A retained fee stays pending when net funds are below it. |
| Expired with active position | Full payment leads to paid if late payments are allowed and quota is available. Exhausted quota leaves expired. | Eligible order can be canceled without a fee. |
| Paid with active position | The API rejects another mark-paid action. Reconfirming the same payment at model level preserves its original date and record. | Empty or zero fee leads to canceled. A retained fee within the total can leave paid when net funds cover it. |
| Canceled | Neither workflow reopens the order. | Rejected even if a no-fee cancellation preserved position rows. |
| Positionless or fee-only | Payment on fee-only orders is outside UC-01/02. | Rejected without an active position. |

For no-fee cancellation, the order retains its total and original position rows and flags. When retaining a fee, active positions are canceled, the fee is stored, and the total is reduced to the fee. Both branches set a cancellation date on the pinned source, including when the retained fee leaves the status paid or pending. The control form rejects EUR 20.01 and excess precision. Its fee-cap message is raised by the form's own cleaning method. Empty and zero normalize to zero. The form accepts a negative value at the scoped boundary; its business interpretation and API treatment still need the teammate contract review. [Order model](../src/pretix/base/models/orders.py) · [Cancellation service](../src/pretix/base/services/orders.py) · [Control form](../src/pretix/control/forms/orders.py) · [REST actions](../src/pretix/api/views/order.py)

## BR-02 decision table and CFG

Order.cancel_allowed evaluates status membership before the count of active positions. Each status row runs with and without an active position.

| Case | Status | No positions | Active positions |
| --- | --- | --- | --- |
| C1 | Pending | False | True |
| C2 | Expired | False | True |
| C3 | Paid | False | True |
| C4 | Canceled | False | False |

For MC/DC, C1 with an active position compared with C4 with an active position isolates the status predicate. C1 with and without an active position isolates the position predicate. The position predicate is skipped by Python for ineligible status. The test still seeds both canceled shapes to show that both produce the same result.

~~~mermaid
flowchart TD
    entry([Entry]) --> status{Eligible status?}
    status -- Yes --> positions{Any active positions?}
    status -- No --> result[Return decision]
    positions -- Yes --> result
    positions -- No --> result
    result --> exit([Exit])
~~~

The five CFG nodes are entry, eligible status, active positions, decision result and exit. Its six edges connect entry to status, status true to positions, status false to decision result, both position outcomes to decision result, and decision result to exit. The cyclomatic complexity is 6 − 5 + 2 = 3. The SonarQube export reports aggregate complexity of 689 for base/models/orders.py, which contains this function. The exported measure is at file granularity.

## Windows white-box coverage

Results from the 30 passing unit cases. Statement and branch counts come from coverage.py 7.17.4. The eight BR-02 cases exercise the Boolean outcomes even though coverage.py reports no separate line-level branch arcs for its single return expression.

| Callable | Statements | Branch arcs | Gaps |
| --- | --- | --- | --- |
| Order.cancel_allowed | 1/1 | 0 tracked | Both conditions exercised in the MCC table. |
| OrderPayment.confirm | 24/24 | 10/10 | Covers repeat, partial, full, canceled and quota paths. |
| OrderPayment._mark_paid_inner | 13/14 | 5/6 | Line 1829 records overpayment, outside the exact or partial payment fixtures. |
| CancelForm.clean_cancellation_fee | 4/4 | 2/2 | Cap acceptance and rejection. |
| _cancel_order | 69/109 | 37/62 | The sample covers no-fee, retained fee, unfunded fee, admission rejection and fee-cap rollback. See the line-level gaps below. |

The uncovered cancellation lines include argument conversions and object lookups at 529–539, pre-existing invoices at 549, gift cards and memberships at 553–575, voucher and existing-fee paths at 582 and 590–595, alternate tax modes and invoice address at 600–602, and invoice or mail handling at 639–643, 656, 667–684 and 693–694. These fixtures use ordinary ticket positions, decimal fees, no invoices and suppressed notifications. See local/sqe/evidence/coverage.json for exact lines and arcs. The whole-module coverage target remains open.

## SonarQube results

| Metric | Initial scan | Coverage imported |
| --- | --- | --- |
| Noncomment lines and cyclomatic complexity | 11,382 lines, 2,564 aggregate complexity | Same source scope |
| Duplicated lines | 1.2% | 1.2% |
| Bugs, vulnerabilities and code smells | 0, 1, 0 | 0, 1, 0 |
| Technical debt | 0 recorded minutes | 0 recorded minutes |
| Reliability, security and maintainability ratings | A, D, A | A, D, A |
| Combined coverage | 0.0% | 20.7% |
| Line coverage | 0.0% | 25.7% |
| Branch coverage | Unavailable | 6.7% |
| Default quality gate | OK | OK |

The analyzer parsed the Windows coverage report. Its source scope includes entire files, so the aggregate coverage includes many order paths beyond the fixtures. The cancellation service contributes the most complexity of the five files, at 827. The vulnerability alert and security rating need triage against the scoped defensive review. The working-copy test file lacked Git blame during the scan. See the handoff for evidence file names and scanner configuration.

## Browser observation

For UC-01 exception 1, the payment form rejected EUR 20.001 and redirected to the pending order detail without showing the field error. The original expectation was an inline error. The Windows browser run and the final redirect in OrderTransition.post support the observation. The executable case verifies the visibly pending order and unchanged stored state. The feedback defect remains open for triage. See local/sqe/evidence/playwright-revised-results and the original expectation in the saved trace. [Control transition](../src/pretix/control/views/orders.py)

## Traceability

| Requirement | Rule | Current coverage and risk |
| --- | --- | --- |
| PAY-01 | BR-01 | Unit full/partial cases, fixture W1, UC-01. R1 and R2. |
| PAY-02 | BR-01 | Unit expired eligible and quota cases, UC-01. R3. |
| PAY-03 | BR-01 | Unit same-payment repeat. API repeat remains open. R1. |
| PAY-04 | BR-01 | Viewer can read in smoke. Member 3 still verifies the denied payment action. R4. |
| CAN-01 | BR-02 and BR-04 | Unit paid/no-fee, fixture W2, UC-02. R2 and R7. |
| CAN-02 | BR-03 and BR-04 | Unit funded and unfunded retained fee. UC-03/04 remain open. R5. |
| CAN-03 | BR-03 | Unit cap boundary and rollback. API and UC-03/06 remain open. R5 and R6. |
| CAN-04 | BR-02 | Unit MCC and invalid states, UC-02 canceled order. API replay remains open. R1 and R7. |
| CAN-05 | BR-02 | UC-02 viewer denial and persisted state. API authorization remains open. R4. |

## Risks and release criteria

Score likelihood × impact on a 1–5 scale. Scores of 15 or more get boundary, negative and stored-state assertions at more than one level where applicable. Use lower-risk checks to cover task behavior and handoffs.

| ID | Risk | Likelihood | Impact | Score | Planned check |
| --- | --- | --- | --- | --- | --- |
| R1 | Duplicate payment or fee on retry | 4 | 5 | 20 | White-box repeat, API replay and controlled recovery |
| R2 | Status updated without matching records | 4 | 5 | 20 | Unit and API/Playwright readbacks |
| R3 | Late payment consumes unavailable quota | 3 | 5 | 15 | Expired-order decision and quota boundary |
| R4 | Viewer can perform a write | 4 | 5 | 20 | Four manager/viewer action decisions |
| R5 | Excess fee or incorrect retained total | 4 | 4 | 16 | EUR 19.99/20.00/20.01 boundary and UI correction |
| R6 | Failed write leaves partial data | 3 | 5 | 15 | Persisted rollback and recovery assertions |
| R7 | Cancellation leaves wrong ticket eligibility | 3 | 4 | 12 | State and position checks after cancellation |
| R8 | Order details slow or fail under load | 3 | 3 | 9 | One-user and five-user k6 workloads |
| R9 | Team handoff delayed by fork access | 4 | 3 | 12 | Local owner work first and access check before teammate PRs |
| R10 | Drift between workstation and CI | 3 | 4 | 12 | Clean Windows fixture setup, versions and run evidence |

| Likelihood \ Impact | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| 5 | — | — | — | — | — |
| 4 | — | — | R9 | R5 | R1, R2, R4 |
| 3 | — | — | R8 | R7, R10 | R3, R6 |
| 2 | — | — | — | — | — |
| 1 | — | — | — | — | — |

The proposed release criteria are zero duplicate business writes in replay and recovery checks, zero unauthorized writes in the four role checks, and order-detail GET p95 of at most 500 ms with fewer than 1% unexpected failures at both workloads. Confirm workload limits with Member 3 before measurements.

Enter a phase with the expected baseline, fixtures and owner. Suspend after a failed reset, a source/runtime mismatch or a missing dependency. Resume after a clean reset or documented correction and repeat the affected check. Start integration once all authored suites and evidence are available. Compare actual and estimated effort and update issues, risks and criteria at each weekly review.

| Work area | Optimistic hours | Most likely hours | Pessimistic hours | Start |
| --- | --- | --- | --- | --- |
| Windows setup, fixtures and planning | 3 | 6 | 10 | Tawassul before teammate access |
| Static analysis, CFG and unit tests | 4 | 7 | 12 | Tawassul after fixture contract |
| OpenAPI, generated cases and API suite | 4 | 8 | 14 | Member 2 on the shared branch |
| Playwright setup and six cases | 6 | 12 | 20 | Tawassul first, teammates after access |
| Usability, accessibility and defensive checks | 4 | 8 | 14 | Member 3 after shared runner |
| Performance and recovery | 3 | 6 | 10 | Member 3 after fixture contract |
| Mutation, CI and final package | 5 | 10 | 18 | Tawassul starts locally and finishes after authored PRs |

These are initial planning estimates. Record each author's actual effort at the weekly review. Record executable requirement coverage as the number of requirements with executed linked checks divided by nine. Report defect count per scoped KLOC and reopened defects divided by resolved defects when the GitHub issue history is available. Report the numerator and denominator next to each result.
