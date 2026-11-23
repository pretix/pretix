# Performance and recovery — Orders W1/W2

Author: Member 3 · Date: 23 Nov 2026 · Evidence: `sqe/evidence/member3/perf/` (environment, k6 console output, k6 summary export and raw per-request JSON for every run, `results.json`) and `sqe/evidence/member3/recovery.xml`.

## 1. Performance (Grafana k6 OSS 2.4.0)

### Operation and limits (fixed before the first measured run — `Documents/Member3-Plan.md` §8)

**Operation:** authenticated `GET /api/v1/organizers/sqe-orders/events/orders/orders/M3R01/` with the Orders Viewer token. It is the read both workflows depend on: W2 reads the state W1 wrote, and every functional test verifies its postconditions with it. It is read-only, so repeated runs start from identical data.

| Workload | p95 limit | Unexpected-failure limit | Why |
|---|---|---|---|
| 1 virtual user | ≤ 300 ms | < 1 % | One JSON read of one order by primary key; a back-office read should feel immediate (≈ 0.1–0.3 s) and is only part of a larger page, so it needs headroom. |
| 5 virtual users | ≤ 800 ms | < 1 % | SQLite and the development server serialise part of the work, so latency grows with concurrency; it must stay well below the 1 s limit for keeping a user's flow of thought. |

An *unexpected failure* is any response that is not HTTP 200, not JSON, or whose `code` is not `M3R01` (k6 `Rate` metric `unexpected_failures`). Both limits are k6 thresholds, so each run's exit code is its verdict.

### Method
- One script (`src/tests/team/perf/order-read.k6.js`) for both workloads: scenario `warmup` (15 s, excluded from thresholds) then `measure` (**75 s at the full user count**, more than the required 60 s). Think time 1 s per iteration (a manager reading the order).
- Same build (commit `297f75796`), same machine, same starting data (fresh reset; the operation does not change data), runs back to back: R1a, R1b (1 VU), R5a, R5b (5 VUs). No other workload ran; ZAP and the browser suites were stopped.
- Server: Django `runserver` with `sqe.windows_perf_settings` (**DEBUG off**, confirmed: an API 404 returns the normal "Not found" page, not Django's technical page) on SQLite.
- Environment (`environment.json`): Windows 11 Pro build 26300, Intel Core i7-11850H (8 cores / 16 threads), 31.7 GB RAM (15.7 GB free at start), Balanced power plan, Python 3.12.10, Django 5.2.19.
- Results are recomputed from the raw per-request stream by `sqe/m3_perf_summary.py`: k6's `{phase:measure}` rate divides by the whole 90 s run, so throughput is measured requests ÷ 75 s; p95 is recomputed with the same interpolation as k6 and matches it exactly.

### Results

| Run | VUs | Requests measured | p95 (ms) | Median (ms) | Max (ms) | Requests/s | Unexpected failures | p95 limit | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| R1a | 1 | 73 | **56.5** | 37.2 | 65.2 | 0.97 | 0.0 % | 300 | PASS |
| R1b | 1 | 72 | **58.3** | 39.0 | 69.9 | 0.96 | 0.0 % | 300 | PASS |
| R5a | 5 | 352 | **135.7** | 66.5 | 293.8 | 4.69 | 0.0 % | 800 | PASS |
| R5b | 5 | 349 | **177.9** | 68.0 | 331.8 | 4.65 | 0.0 % | 800 | PASS |

### Interpretation
- **Both workloads meet their limits with a wide margin**: p95 is 19 % of the 1-VU limit and at most 22 % of the 5-VU limit; no request failed (0 of 846 measured).
- **Repeatability.** The two 1-VU runs differ by 1.8 ms at p95 (3 %), so the single-user measurement is stable. The two 5-VU runs differ by 42 ms at p95 (27 % of their mean) while their medians differ by only 1.5 ms: the variation is in the tail, which is expected for a single-process development server on a laptop (scheduler, antivirus and SQLite file locking).
- **Scaling 1 → 5 users.** Throughput grows almost linearly (0.97 → 4.7 requests/s, ×4.8) because users spend most of their time in think time; the median latency roughly doubles (38 → 67 ms) and p95 rises 2.4–3.1×, i.e. requests start to queue behind each other in the single server process.
- **Limits of the evidence.** These are relative measurements of a development stack (runserver + SQLite + Windows workstation), not production capacity. A production pretix runs gunicorn workers behind nginx on PostgreSQL; the measured operation would be expected to be faster per request and to scale further. Release criterion 3 ("order read p95 within limit, < 1 % unexpected failures at both workloads") is **met** for this environment.

## 2. Failure and recovery (pytest, `src/tests/team/recovery/test_recovery.py`)

Run with `sqe\windows.ps1 recovery` (same SQLite unit-test settings as the white-box suite). Each test uses a **test double** (`unittest.mock.patch`) to make a dependency fail before a state-changing write completes, re-reads the persisted state from the database, restores the dependency, retries, and asserts the final state with no duplicate business records.

| ID | State-changing operation | Dependency made unavailable | Persisted state after the failure | After restore + retry | Replay | Result |
|---|---|---|---|---|---|---|
| REC-01 | W2 cancel a paid order keeping a 5.00 fee | ticket-secret generator (`assign_ticket_secret`), fails **before the first write** | identical to before (paid, total 20.00, 1 active position, 0 fees) | paid, total 5.00, position canceled, **exactly 1** cancellation fee, payment kept | second cancel rejected (`OrderError`), still 1 fee | Pass |
| REC-01b | same | transaction ledger (`Order.create_transactions`), fails **after** the order, position and fee were written | identical to before — the atomic block in `_cancel_order` rolled the writes back | as REC-01 | as REC-01 | Pass |
| REC-02 | W1 confirm a full 20.00 manual payment on a pending order | audit-log store, rejects the "order paid" entry | **payment confirmed, order still pending** (partial state) | — | — | Pass (documents the state) |
| REC-02b | same, then retry `confirm()` | restored | — | **order still pending**: `confirm()` returns early for an already-confirmed payment | — | Expected failure (strict xfail) — **defect D-04** |
| REC-02c | same, then the control panel's recovery path (`_mark_order_paid` on the last confirmed payment, used when nothing is outstanding) | restored | — | order paid, **1** confirmed payment, no duplicate | — | Pass |

Result: **4 passed, 1 expected failure.** No duplicate fees or payments in any path.

**Sensitivity check (do the tests detect what they claim?).** A temporary probe replaced `transaction.atomic` in the cancellation service with a no-op and re-ran REC-01 and REC-01b: **REC-01b failed** (the order, position and fee were left half-cancelled), proving it detects missing atomicity; REC-01 still passed because its failure happens before any write, so it is documented as "failure before the first write" rather than as an atomicity test.

**D-04 (from REC-02/02b).** `OrderPayment.confirm()` commits the payment as confirmed in one transaction and marks the order paid in a second (`base/models/orders.py:1890-1956`). If anything fails in between (here the audit log; in production a signal receiver or plugin), the payment is confirmed but the order stays pending, and simply retrying the confirmation does nothing. The data is consistent again only after a manual "mark as paid" with amount 0.00 (REC-02c). *Not executed, from code reading only:* the API `mark_paid` action would look for a pending payment of the outstanding amount (now 0.00), create a new 0.00 manual payment and confirm it, leaving an extra zero-value payment record (`api/views/order.py:395-440`); this should be checked by the API owner. Recommended correction: run both steps in one transaction, or make `confirm()` idempotent by completing `_mark_order_paid` when the payment is already confirmed but the order is not paid. Linked risks: R2 (status without matching records), R6 (partial data on failure), R16.

SQLite ignores `select_for_update`, so these tests show transactional atomicity, not lock-based concurrency safety.
