# Member 3 — Test plan for use cases, usability, accessibility, security, performance and recovery

Owner: Member 3 (GitHub `Zubairilyas1`) · Branch: `sqe/browser-quality` · Baseline: upstream `526a79c7d`, team fork `tawassulAkbr/pretix`
Status: **Draft v0.1 — 23 Nov 2026.** Update the version and the change log at the bottom every time this plan changes. The brief says "keep it updated".

This plan covers the rubric items Member 3 is examined on:

| Rubric component | Marks | Section here |
|---|---|---|
| Use case specification (shared with the other members, 2 UCs each) | 3 | §4 |
| Use case test automation (shared) | 6 | §4 |
| Usability and accessibility evaluation | 5 | §5, §6 |
| Defensive security | 6 | §7 |
| Performance and recovery | 5 | §8, §9 |
| Defect management, monitoring and completion report (shared) | 7 + 5 | §11 |
| Viva: individual explanation, live task | part of 20 | §14 |

---

## 1. Facts from the source that shape this plan

I verified these by reading the pinned code. They are facts, not assumptions.

| # | Fact | Where | Consequence for my tests |
|---|---|---|---|
| F1 | The cancel form **re-renders with field errors** when invalid (`return self.get(...)`). | `src/pretix/control/views/orders.py` (OrderTransition.post, cancel branch) | W2 (cancellation) is the right workflow for the brief's "error explains what to correct, then correct it" test. |
| F2 | The payment form **silently redirects** when invalid. The `elif` chain falls through to `redirect(self.get_order_url())` without showing errors. | same view, first `if ... and self.mark_paid_form.is_valid()` | Any invalid payment input (bad date, bad precision) will **not** show an error. This is the defect Tawassul already saw in UC-01. My UC-05 invalid-date exception reproduces it. |
| F3 | `OrderTransition.permission = 'event.orders:write'` is enforced server-side by `EventPermissionRequiredMixin`. | `control/views/orders.py:1452`, `control/permissions.py:82` | A viewer opening `/transition?status=c` directly should get **403**. Hiding the link (all that UC-02 exc 1 checks) is **not** access control. My access tests must hit the URL and the API directly. |
| F4 | API write actions require `write_permission = 'event.orders:write'` for non-safe methods. | `api/views/order.py:342`, `api/auth/permission.py:57` | Viewer token POST `mark_paid/` and `mark_canceled/` should return **403**. |
| F5 | `cancellation_fee` has a max (order total) but **no minimum** in the form or the API. | `control/forms/orders.py:170`, `api/views/order.py:458` | Hypothesis H1 (below): a negative fee may be accepted. |
| F6 | `MarkPaidForm.amount` has **no minimum**. | `control/forms/orders.py:244`, `helpers/money.py:48` | Hypothesis H2: a negative manual payment may be accepted. |
| F7 | `OrderPayment.confirm` commits the payment as *confirmed* in one transaction, then marks the order paid in a **second** step. Retrying confirm on an already-confirmed payment returns early. | `base/models/orders.py:1890–1955` | Hypothesis H4: a failure between the two steps could leave a confirmed payment on an unpaid order, and a retry might not recover it. This is my recovery-test target. |
| F8 | `_cancel_order` runs inside one `transaction.atomic()`. | `base/services/orders.py:525` | A failure part-way through cancellation should roll back **everything**. This is the recovery-test oracle for W2. |
| F9 | Session cookie: `HttpOnly` is always set. `Secure`, the `__Host-` prefix and `SameSite=None` are applied **only when the request scheme is https**. | `settings.py:455–458`, `multidomain/middlewares.py:184–233`, `helpers/cookies.py:29–48` | On our http loopback, ZAP **will** flag the cookie for missing Secure/SameSite. I must explain from the source that this depends on the scheme, not report it naively as a vulnerability. |
| F10 | `X_FRAME_OPTIONS = 'DENY'`. A CSP is built per response by middleware. | `settings.py:574`, `base/middleware.py:321–436` | These are controls I can corroborate against ZAP's header findings. |
| F11 | Neither the API nor the settings use `ATOMIC_REQUESTS`. | grep of `src/pretix` | API `mark_paid` is **not** wrapped in one transaction (unlike the control view, which is `@transaction.atomic`). This matters for H3/H4. |
| F12 | `fixture_config()` **reuses** `local/sqe/windows/fixtures.json` if it already exists. | `sqe/orders_fixtures.py:30` | When I add new order aliases, I must delete `fixtures.json` once (credentials regenerate) or they won't appear in the JSON that Playwright reads. |
| F13 | `windows_settings.py` hard-codes `DEBUG = True`, and the server is Django `runserver` on SQLite. | `sqe/windows_settings.py` | Performance numbers are a **test-environment** measurement, not production capacity. I need a DEBUG-off settings variant for k6 (§8). |

### Hypotheses to confirm or reject. Never report one as a defect until a test shows it.

| ID | Hypothesis | How I test it | Expected per business rule | If confirmed |
|---|---|---|---|---|
| H1 | A negative cancellation fee (e.g. −0.01) is accepted. The order then stays "paid" with a negative total. | UC-06 exc 2 (UI) and one API probe | Reject: a fee must be ≥ 0 | Major defect. GitHub issue, RCA #1 (5 Whys + fishbone). |
| H2 | A negative manual payment amount is accepted as a confirmed payment. | UC-05 boundary probe | Reject: amount must be > 0 | Defect. Issue; possibly RCA #2. |
| H3 | API `mark_paid` on an expired order with exhausted quota returns 400 but leaves a **confirmed** payment. The UI marks it *failed* instead. | Hand to **Member 2** (API owner). I only note it. | Same outcome as the UI: payment *failed* | Endpoint weakness (Member 2's finding). |
| H4 | If the step after the payment is confirmed fails, the order stays pending with a confirmed payment, and retrying `confirm` is a no-op. | REC-02 (§9) | Consistent state after retry | Major defect candidate. RCA #2. |
| H5 | Invalid payment-form input gives no inline error (same root cause as Tawassul's UC-01 exc 1). | UC-05 exc 1 | Inline error explaining the fix | Same issue as UC-01's. Link, don't duplicate. |

---

## 2. Scope

**In scope (mine):** UC-05 and UC-06 (specification and automation), the two automated usability task tests, keyboard navigation, Lighthouse and axe-core before and after one screen fix, the route and data inventory, the access matrix with automated checks, ZAP passive scan, a review of at least 2 controls (I plan 4), dependency audit, k6 workloads (1 VU and 5 VU, each ×2), and an automated failure-and-recovery test.

**Out of scope:** active or aggressive scanning (the brief says passive only), real payment providers, real e-mail, refunds after the refund prompt, the presale shop, other modules, production-scale load.

**Shared with the team:** risk register rows, RTM rows, GitHub issues, weekly reports, completion report.

---

## 3. Environment and tools

My machine has Python 3.12.10 (pretix needs ≥ 3.11, so this is fine), Node 24.18 (matches `.node-version`), Git and Docker. **Missing:** k6, ZAP, Lighthouse, Java, `gh`, and the project venv.

| Tool | Install on Windows | Version policy |
|---|---|---|
| Project venv | `uv venv .\local\sqe\venv --python <my python.exe>`, then `uv pip install -e ".[dev]"` (see `sqe/handoff.md`) | Record `python --version` and `pip freeze` |
| Playwright + Chromium | already pinned: `@playwright/test 1.65.1` in `src/tests/team/e2e` | do not bump (shared) |
| `@axe-core/playwright` | `npm i -D -E @axe-core/playwright` in the e2e folder | exact pin (`-E`) |
| Lighthouse | `npm i -D -E lighthouse` in the e2e folder, then use the Node API | exact pin |
| k6 OSS | `winget install GrafanaLabs.k6` | record `k6 version` |
| OWASP ZAP | Windows installer from zaproxy.org (it **bundles its own Java**, so there is no separate JDK to install) | record the version from Help → About |
| pip-audit | `uv pip install pip-audit` into the venv | record version |
| npm audit | built in | record npm version |
| gh CLI (optional) | `winget install GitHub.cli` | for issues and PRs |

Deliverable: `sqe/member3/tool-versions.md`, with each tool, its exact version, and the command used to print the version.

**Why native ZAP rather than Docker:** a container's `localhost` is not the host's. Reaching the app as `host.docker.internal` sends a Host header that `ALLOWED_HOSTS = ['127.0.0.1', 'localhost']` rejects. Native ZAP avoids changing app config.

---

## 4. Use cases UC-05 and UC-06

### 4.1 Changes to the original plan, and why

Tawassul's draft of UC-05 and UC-06 **duplicates flows that other members already own**. The brief says "count each executable case once", so duplicates earn nothing.

| Draft flow | Duplicates | My replacement |
|---|---|---|
| UC-05 main "settle an expired order with available quota" | UC-01 alt 2 (identical) | Partial payment, then the remainder |
| UC-06 alt "retain a valid fee" | UC-03 main (Member 2) | Abandon with "No, take me back" |
| UC-06 exc "viewer cannot cancel" | UC-02 exc 1 (link hidden) | Moved to the security suite and strengthened to a direct-URL 403 (§7). UC-06 exc 2 becomes the negative-fee boundary (H1). |

**Action:** agree these with Tawassul and Member 2 before coding. Record the agreement in the weekly report.

### 4.2 Fixtures I need

I'll add these to `ORDERS` in `sqe/orders_fixtures.py` with an `M3` prefix so they can't collide with the other members'. All orders are EUR 20.00 with one position unless stated.

| Alias | Code | Status | Extra seeding | Used by |
|---|---|---|---|---|
| `m3_partial` | M3P01 | n | – | UC-05 main |
| `m3_reuse` | M3P02 | n | one **created** manual payment of 20.00 | UC-05 alt 1 |
| `m3_overpay` | M3P03 | n | – | UC-05 alt 2 |
| `m3_bad_date` | M3P04 | n | – | UC-05 exc 1 |
| `m3_canceled` | M3P05 | c | – | UC-05 exc 2 |
| `m3_neg_amount` | M3P06 | n | – | H2 probe |
| `m3_kbd_paid` | M3K01 | p | confirmed 20.00 | UC-06 main |
| `m3_zero_fee` | M3K02 | n | – | UC-06 alt 1 |
| `m3_abandon` | M3K03 | p | confirmed 20.00 | UC-06 alt 2 |
| `m3_fee_fix` | M3K04 | p | confirmed 20.00 | UC-06 exc 1 / USA-02 |
| `m3_neg_fee` | M3K05 | p | confirmed 20.00 | UC-06 exc 2 (H1) |
| `m3_sec_pay` / `m3_sec_cancel` | M3S01 / M3S02 | n / p | – | access matrix (UI, viewer) |
| `m3_sec_api_pay` / `m3_sec_api_cancel` | M3S03 / M3S04 | n / p | – | access matrix (API, viewer) |
| `m3_sec_mgr_pay` / `m3_sec_mgr_cancel` | M3S05 / M3S06 | n / p | – | access matrix (manager allowed) |
| `m3_lh_pending` / `m3_lh_paid` | M3L01 / M3L02 | n / p | – | Lighthouse and axe (read-only) |
| `m3_perf` | M3R01 | p | – | k6 (read-only) |

`verify()` already loops over `ORDERS`, so the contract check extends automatically. The created payment on M3P02 is not confirmed, so the count stays correct. Remember F12: delete `fixtures.json` once.

### 4.3 UC-05 — Settle an order through exceptional manual payments (W1)

- **Actor:** Orders Manager. **Trigger:** money arrives that doesn't match the simple "one payment, exact total" case.
- **Preconditions:** the manager is logged in; the order is in the stated state; e-mail notifications are unchecked.
- **Requirements:** PAY-01, PAY-02, PAY-03. **Risks:** R1, R2, R5.

| Flow | Steps | Visible result asserted | Persisted postcondition asserted (API readback) |
|---|---|---|---|
| **Main.** Partial payment, then the remainder (M3P01) | Mark as paid → amount 12.00 → Create payment; then Mark as paid again → the prefilled amount is 8.00 → Create payment | 1st: success message, header still *Pending*. 2nd: success message, *Paid*. The prefilled amount on the 2nd form equals 8.00. | After the 1st payment: status `n`, 1 confirmed 12.00. After the 2nd: status `p`, exactly 2 confirmed payments summing to 20.00, positions unchanged. |
| **Alt 1.** Reuse the seeded matching manual payment (M3P02) | Mark as paid → 20.00 → Create payment | success, *Paid* | status `p`. **Payment count stays 1**: the created payment became confirmed and no duplicate was made. This exercises the `payments.get(... amount=ps)` reuse branch, which addresses R1. |
| **Alt 2.** Overpayment (M3P03) | Mark as paid → 25.00 | success, *Paid* | status `p`, 1 confirmed 25.00, total still 20.00. This exercises the overpaid branch, which Tawassul's unit tests leave uncovered (`_mark_paid_inner` line 1829). |
| **Exc 1.** Invalid payment date (M3P04) | Mark as paid → date `2026-13-45` → Create payment | No success message; the order is still *Pending*. **Plus** a `test.fail()`-annotated assertion that an inline date error is shown (expected to fail while H5 is open). | State identical to before: 0 payments created. |
| **Exc 2.** Canceled order (M3P05) | Open the order | The "Mark as paid" link is absent. GET `/transition?status=p` returns **405**. | Unchanged. |
| *Probe (not a UC flow)*. Negative amount −0.01 (M3P06) | Mark as paid → −0.01 | Tests H2: expect rejection | Expect no confirmed payment |

### 4.4 UC-06 — Cancel an order using only the keyboard (W2)

- **Actor:** Orders Manager who uses the keyboard only (accessibility persona).
- **Preconditions:** as above. **Requirements:** CAN-01, CAN-02, CAN-03. **Risks:** R5, R7, R17.

| Flow | Steps (keyboard only: Tab, Shift+Tab, Space, Enter) | Visible result | Persisted postcondition |
|---|---|---|---|
| **Main.** No fee (M3K01, paid) | Tab to the "Cancel order" link → Enter. Tab through the form, asserting focus order **fee → Notify by email → Comment → No, take me back → Yes, cancel order**. Space to untick e-mail. Focus "Yes, cancel order" → Enter. | Cancellation success or refund prompt | status `c`, `cancellation_date` set, 0 cancellation fees, the confirmed payment is still present, the position rows still exist |
| **Alt 1.** Zero fee on a pending order (M3K02) | Type `0.00` in the fee field → Enter | success | status `c`, 0 fees. This is EP: "zero" is a different class from UC-02's "empty". |
| **Alt 2.** Abandon (M3K03) | Open the cancel form → Tab to "No, take me back" → Enter | back on the order detail, still *Paid* | identical to before |
| **Exc 1.** Above-cap fee, then correct it (M3K04). **This is USA-02.** | Fee 20.01 → Enter → assert the inline error → fix the fee to 19.99 → Enter | Error text contains "cannot be higher than the total amount". The field is marked invalid (`has-error` / `aria-invalid`). The typed value is kept. Then success. | After rejection: unchanged (status `p`, 0 fees). After correction: status `p` (20.00 paid ≥ 19.99), total 19.99, all positions canceled, exactly 1 cancellation fee of 19.99. |
| **Exc 2.** Negative fee −0.01 (M3K05). BVA just below the lower limit 0. | Fee −0.01 → Enter | **Expected (rule):** inline error, no change. | If H1 is confirmed, keep the test as `test.fail()` linked to the GitHub issue until it's fixed, and record the observed state as evidence. |

Fee-boundary BVA summary for my flows: **−0.01** (just below 0), **0.00** (at 0), **19.99 / 20.01** (below and above the cap, which Member 2 also covers at API level; at UI level, counted once per level).

### 4.5 Implementation rules

- File `src/tests/team/e2e/uc05-uc06.spec.js`. Reuse `orders.open()` and `orders.read()` from `orders.js`. Put the case ID in every test title (e.g. `UC-06 exc 1 ...`).
- Use role and label locators only; no CSS or XPath for actions. Use web-first `expect` and no `waitForTimeout`.
- Each test runs **before → action → after** readbacks and asserts the full diff, not just status (the same pattern as UC-01/02).
- Put business constants (`TOTAL`, `FEE_CAP`, boundary values) in **one** module, `e2e/rules.js`. A live-task rule change then means one edit (§14).

---

## 5. Usability task tests (brief §3)

| ID | Workflow | Content | Also counts as |
|---|---|---|---|
| USA-01 | W1 | Open the payment task screen → fill with test data → assert the confirmation "The payment has been created successfully." and the order status | UC-05 main |
| USA-02 | W2 | **Keyboard only.** Assert the focus order through the required fields and the submit button. Submit fee 20.01 by keyboard → assert the error **explains the fix** (names the limit) → correct → submit by keyboard → assert confirmation | UC-06 exc 1 |

Focus-order assertion technique: press `Tab` repeatedly and after each press read `document.activeElement` (`accessible name` + role) into an array; assert the subsequence equals the expected order. This is robust to header and navigation links before the form.

---

## 6. Accessibility evaluation

### 6.1 Screens (one key screen per use case, plus the shared screen)

| Screen | URL | Fixture | Use cases |
|---|---|---|---|
| S1 Order detail | `/control/event/sqe-orders/orders/orders/M3L02/` | paid, read-only | all |
| S2 Mark as paid form | `.../orders/M3L01/transition?status=p` | pending, read-only | UC-01, UC-05 |
| S3 Cancel form | `.../orders/M3L02/transition?status=c` | paid, read-only | UC-02, UC-03, UC-06 |

Opening the transition form with GET does not change data, so the same orders can be scanned repeatedly.

### 6.2 Method

1. **axe-core:** `a11y.spec.js` logs in, visits each screen, runs `new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']).analyze()`, and saves the JSON to `evidence/a11y/<phase>/axe-S#.json`.
2. **Lighthouse while logged in:** script `tools/lighthouse.mjs`. Launch Chromium with `--remote-debugging-port=9222` through Playwright, log in, then call the Lighthouse Node API on the same port (it shares the session cookie). Categories: `accessibility`, `best-practices`, `seo`. Use the desktop preset with fixed viewport and throttling. Run **3 times per screen and report the median** (Lighthouse scores vary a little). Save HTML and JSON.
3. **De-duplication** (brief: "count once"): Lighthouse's accessibility audits *are* axe rules, so their IDs match. `tools/merge-a11y.mjs` keys each finding on `(ruleId, CSS selector)` and outputs one table: element, rule, WCAG criterion, impact, **user impact in plain words**, proposed fix, severity, risk ID, and found-by (axe / LH / both).
4. **Prioritise:** axe impact (critical > serious > moderate > minor) × how often the screen is used in the workflows.

### 6.3 The screen fix

Choose **after** the baseline, using the merged table. The selection rule is the screen with the most serious and critical findings that I can fix in templates without changing behaviour.

- **Expected candidate: S3 Cancel form**, because it's in my use cases. A known small issue is that both `cancel.html` and `pay.html` put an invalid `href=""` attribute on `<form>`. The rest depends on the scan.
- **Strong option to discuss with Tawassul:** fixing **F2** (the payment form doesn't show its errors) on S2. That is a genuine usability fix. It could also serve as the brief's "documented fix through a PR that fails before and passes after", since UC-01 exc 1 and UC-05 exc 1 would then assert the inline error.

**Before/after protocol:** same fixtures (reset), same build except the fix commit, same Chromium, same Lighthouse preset, 3 runs each. Report the audit-level difference (findings resolved or new), not just scores. Save everything under `sqe/evidence/member3/a11y/{before,after}/`.

---

## 7. Defensive security assessment

### 7.1 Attack surface and route inventory → `sqe/member3/security-assessment.md`

| Route | Method | Auth | Workflow | Data in / out |
|---|---|---|---|---|
| `/control/login` | GET/POST | none → session | both | e-mail, password → `pretix_session`, `pretix_csrftoken` |
| `/control/event/{org}/{ev}/orders/{code}/` | GET | session, `orders:read` | both | order, positions, payments, customer e-mail |
| `.../orders/{code}/transition?status=p` | GET/POST | session + CSRF, `orders:write` | W1 | amount, payment_date, send_email, force |
| `.../orders/{code}/transition?status=c` | GET/POST | session + CSRF, `orders:write` | W2 | cancellation_fee, send_email, comment, cancel_invoice |
| `/api/v1/organizers/{org}/events/{ev}/orders/{code}/` | GET | `Token`, `orders:read` | both | full order JSON (PII: e-mail) |
| `.../orders/{code}/mark_paid/` | POST | `Token`, `orders:write` | W1 | send_email |
| `.../orders/{code}/mark_canceled/` | POST | `Token`, `orders:write` | W2 | send_email, comment, cancellation_fee |

### 7.2 Access matrix with automated checks → `access.spec.js`

The brief needs ≥ 4 decisions; I plan **12**, covering both channels (UI and API) and three subjects.

| ID | Role | Action | Expected | Persisted check |
|---|---|---|---|---|
| AC-01 | Manager | UI: submit payment (M3S05) | allowed, success | `p` |
| AC-02 | Manager | UI: submit cancel (M3S06) | allowed, success | `c` |
| AC-03 | Viewer | UI: view order detail | allowed 200 | – |
| AC-04 | Viewer | UI: GET pay form directly (M3S01) | **403** | unchanged |
| AC-05 | Viewer | UI: POST payment with a valid CSRF token (M3S01) | **403** | unchanged |
| AC-06 | Viewer | UI: GET cancel form directly (M3S02) | **403** | unchanged |
| AC-07 | Viewer | UI: POST cancel with a valid CSRF token (M3S02) | **403** | unchanged |
| AC-08 | Viewer | API: GET order | 200 | – |
| AC-09 | Viewer | API: POST `mark_paid/` (M3S03) | **403** | unchanged |
| AC-10 | Viewer | API: POST `mark_canceled/` (M3S04) | **403** | unchanged |
| AC-11 | Anonymous | UI: GET order detail | redirect to login | – |
| AC-12 | Anonymous | API: GET order | 401 | – |

- **POST technique for AC-05/07:** after the viewer logs in, read the `pretix_csrftoken` cookie and send `page.request.post(url, { form: {...}, headers: { 'X-CSRFToken': token, Referer: url } })`. This proves the **server-side role check** blocks the request, not the CSRF check.
- Each test records **role, action, expected, observed, evidence**: the status code, a sanitized response excerpt and the before/after readback. It attaches them as JSON through `testInfo.attach`, and a reporter writes `access-matrix-results.md`.
- **Stretch:** a second event in the same organizer, to check that the viewer token can't read another event's order (expect 404). This is relevant because upstream fixed a missing organizer check (CVE-2026-131165) at our baseline.

### 7.3 ZAP passive scan

1. Start ZAP in daemon mode: `zap.bat -daemon -port 8090 -config api.disablekey=true` (local only), with **no active scan, no spider attack**.
2. Run the whole Playwright suite (UC-05/06 + access + usability) with `use.proxy = { server: 'http://127.0.0.1:8090' }`. **Critical gotcha:** Chromium bypasses proxies for loopback by default, so add launch arg `--proxy-bypass-list=<-loopback>`. Then confirm ZAP's history shows `127.0.0.1:18081` requests **before** collecting results. Without this the scan is empty, which is risk R11.
3. Export the alerts as JSON and the HTML report through the ZAP API (`/JSON/core/view/alerts/`, `/OTHER/core/other/htmlreport/`) to `sqe/evidence/member3/zap/`.
4. Triage each alert as true positive, environment-dependent (http loopback), or false positive. Corroborate each with source.

### 7.4 Control reviews (brief ≥ 2; I plan 4)

| Control | Observation method | Source corroboration |
|---|---|---|
| C1 Session cookie attributes | ZAP cookie alerts + Playwright `context.cookies()` | F9: HttpOnly always set; Secure/`__Host-`/SameSite only on https (`multidomain/middlewares.py:184–233`). I'll explain why the http-loopback alert does not apply to https deployments, and recommend enforcing HTTPS. |
| C2 Server-side role enforcement | AC-04…AC-10 | F3, F4 |
| C3 CSRF on state-changing UI POST | One manager POST **without** a token → expect 403, state unchanged | Django `CsrfViewMiddleware`, `{% csrf_token %}` in `cancel.html` / `pay.html` |
| C4 Security headers | ZAP header alerts | F10: `X-Frame-Options: DENY`, CSP middleware |

### 7.5 Dependency audit

- `pip-audit` over the project venv with JSON output, plus `pip freeze` to record every package and version checked.
- `npm audit --json` for the root `package.json` (Vite build) and for `src/tests/team/e2e`.
- **For each finding:** component, installed version, advisory ID, evidence, **reachability** (is it used in the W1/W2 path?), likely impact, recommended fix version, and the linked risk.
- If nothing is found, document the verified clean result with versions. The brief gives credit for that.

---

## 8. Performance (k6)

**Operation:** authenticated API `GET /api/v1/organizers/sqe-orders/events/orders/orders/M3R01/`, using the viewer token.
- **Why this operation:** it is the read both workflows depend on. W2 reads the state W1 wrote, and it is how every test verifies postconditions. It's read-only, so runs are repeatable on identical starting data, and token auth avoids the CSRF and session noise of the HTML pages.

**Limits, fixed before the first measured run (they must not change after seeing results):**

| Workload | p95 limit | Unexpected-failure limit | Reasoning |
|---|---|---|---|
| 1 VU | ≤ 300 ms | < 1 % | One JSON read of one order by primary key. A back-office API should feel instant (< 0.1–0.3 s is perceived as immediate). It's a component of larger pages, so it needs headroom. |
| 5 VU | ≤ 800 ms | < 1 % | SQLite and the dev server serialize part of the work, so latency rises with concurrency. It must stay well under 1 s, the limit for keeping a user's flow of thought. |

An "unexpected failure" is any response that is not 200, not JSON, or whose `code` ≠ M3R01. These are checked through a k6 `Rate` metric and **enforced as k6 thresholds**, so the run's exit code itself shows pass or fail.

**Script design (`src/tests/team/perf/order-read.k6.js`):**
- Two scenarios per run: `warmup` (constant VUs, 15 s, excluded from thresholds) and `measure` (constant VUs, **75 s**, starting at 15 s, so more than 60 s at the full user count).
- Thresholds are tagged on `{scenario:measure}`.
- Think time `sleep(1)`, which models a manager reading the order. Document this choice.
- Use the same script with a `VUS` env variable (1 or 5).

**Controlled conditions (brief: same build, machine and starting data):**
- Add `sqe/windows_perf_settings.py` = `windows_settings` with `DEBUG = False`. DEBUG keeps every SQL query in memory and slows responses.
- Run sequence: reset → start the server → R1a → R1b → R5a → R5b. Do not reset between runs, because the operation is read-only and the data is identical.
- Record the commit SHA, CPU, RAM, Windows build, Python, Django and k6 versions, and power plan. Close heavy applications. Make no other load.
- Save the raw output: `k6 run --summary-export ... --out json=...` plus the console log, under `sqe/evidence/member3/perf/`.

**Report table:** run, VUs, p95 (ms), requests/s, unexpected failures %, pass/fail per limit. Interpret the variance between repeated runs and what changes from 1 → 5 VUs.
- **Caveat to state plainly:** dev server + SQLite + Windows workstation means these are *relative* findings, not production capacity.

---

## 9. Failure and recovery (automated, pytest)

These live in `src/tests/team/recovery/test_recovery.py`. They run under the same Django test settings as Tawassul's unit suite, so CI can run them, and use `unittest.mock.patch` as the **test double** for a dependency.

| ID | Operation | Injected failure (test double) | Assert after failure | Restore and retry | Final assertion |
|---|---|---|---|---|---|
| REC-01 | W2 cancel with a retained fee of 5.00 on a paid order | `assign_ticket_secret` (ticket-secret generator) raises `ConnectionError` **mid-loop, before** `order.save` | Rollback is complete: status `p`, total 20.00, 0 positions canceled, **0 fee rows**, transaction count unchanged | Stop the patch, call `cancel_order` again | status `p`, total 5.00, all positions canceled, **exactly 1** cancellation fee. A third call raises `OrderError` and still leaves exactly 1 fee (no duplicate on replay). |
| REC-01b | Same | `Order.create_transactions` raises **after** `order.save` but inside the atomic block | Same full rollback (shows the atomic boundary covers late failures) | retry | same as REC-01 |
| REC-02 | W1 confirm a full manual payment on a pending order | the `order_paid` signal receiver (the plugin/notification dependency) raises inside `_mark_paid_inner` | **Observe**, then compare with the expectation "order and payment consistent" → tests H4 | Remove the receiver; retry `confirm()`, then retry via the API path | Expected: order `p`, exactly 1 confirmed payment of 20.00. If H4 is confirmed, the test documents the inconsistent state and becomes a `xfail` linked to an issue, and the issue gets an RCA. |

Each test reads state **fresh from the DB** (`refresh_from_db` or new queries), never from in-memory objects.

Brief caveat to write in the report: SQLite ignores `select_for_update`, so these tests show transactional atomicity, **not** lock-based concurrency safety.

---

## 10. Risks owned or added by me (to merge into the team register)

Scored likelihood × impact on 1–5 scales. Numbering continues from Tawassul's R1–R10, to be agreed.

| ID | Type | Risk | L | I | Score | Mitigation / technique |
|---|---|---|---|---|---|---|
| R11 | Project | Chromium bypasses the proxy for loopback, so ZAP records nothing | 4 | 3 | 12 | `--proxy-bypass-list=<-loopback>` and confirm the ZAP history before collecting |
| R12 | Project | Fixture collisions and shared-DB state across members' suites | 3 | 4 | 12 | `M3` aliases, reset before each suite, one worker |
| R13 | Project | Perf numbers not representative (DEBUG, runserver, SQLite) | 4 | 3 | 12 | DEBUG-off perf settings, fixed conditions, caveat stated |
| R14 | Project | Lighthouse score variance hides a real before/after difference | 3 | 2 | 6 | 3-run median; compare audits, not only scores |
| R15 | Product | Negative fee or payment accepted (H1/H2) → negative totals, wrong revenue | 3 | 5 | **15** | BVA below 0 in UI and API; issue + RCA if confirmed |
| R16 | Product | Partial state when payment confirmation fails part-way (H4) | 2 | 5 | 10 | REC-02 |
| R17 | Product | Keyboard or assistive-technology users cannot complete cancellation | 3 | 4 | 12 | USA-02, axe, Lighthouse, screen fix |
| R18 | Product | Session cookie without Secure/SameSite if deployed on http | 2 | 4 | 8 | C1 review, deployment recommendation |

Links to existing high risks: **R1** (duplicates) → UC-05 alt 1, REC-01/02 · **R4** (viewer writes) → AC-04…AC-10 · **R6** (partial data on failure) → REC-01/01b/02 · **R5** (fee errors) → UC-06 exc 1/2 · **R8** (perf) → §8.

---

## 11. Defects, reporting, exit criteria

**Defects:** every confirmed failure becomes a GitHub Issue on the fork, with severity, priority, status, triage decision, the risk ID, and reproduction steps from the test ID. Issues are disabled by default on forks, so Tawassul must enable them.
- H1 and H4, if confirmed, are my candidates for the **2 major-defect RCAs**: 5 Whys + fishbone (people / process / code / tools / environment / requirements), with corrective and preventive actions.
- Categories for the team Pareto: validation, access control, accessibility, transaction integrity, usability feedback, configuration.

**My exit criteria (measurable; the first three are tied to the highest risks):**

| # | Criterion | Target | Risk |
|---|---|---|---|
| E1 | Unauthorized writes observed in the access checks | **0 of 12** decisions wrong | R4 (20) |
| E2 | Duplicate business records after failure, retry and replay | **0** | R1 (20), R6 (15) |
| E3 | Negative or above-cap fee persisted | **0** (or an open defect with a hold recommendation) | R15 (15), R5 (16) |
| E4 | UC-05/06 flows automated and executed | **10 / 10**, no unexplained failures | – |
| E5 | Serious or critical axe violations on the fixed screen after the fix | **0**, and LH accessibility ≥ baseline | R17 |
| E6 | k6 limits | all 4 runs meet the §8 limits | R8 |
| E7 | High or critical dependency advisories without a triage decision | **0** | – |

The team's 3 release criteria (Tawassul's draft) match E2, E1 and E6. I report actual vs target for them.

**Suspension / resumption:** suspend if a reset fails, the app won't start, or another member's fixture change breaks the `M3` aliases. Resume after a clean reset + `verify`, and rerun the affected suite in full.

---

## 12. Estimates (three-point, hours) and schedule

PERT: E = (O + 4M + P) / 6, SD = (P − O) / 6. I log actual hours next to each row at every weekly review.

| Work package | O | M | P | E | Actual |
|---|---|---|---|---|---|
| WP1 Environment, tools, fixtures | 2 | 4 | 8 | 4.3 | |
| WP2 UC-05/06 specifications | 2 | 3 | 5 | 3.2 | |
| WP3 UC-05/06 automation | 5 | 8 | 14 | 8.5 | |
| WP4 Usability tests (USA-01/02) | 2 | 3 | 5 | 3.2 | |
| WP5 Lighthouse + axe baseline, merge, fix, rerun | 4 | 7 | 12 | 7.3 | |
| WP6 Security (inventory, matrix, ZAP, controls, audit) | 5 | 8 | 14 | 8.5 | |
| WP7 Performance (k6, 4 runs, report) | 3 | 5 | 9 | 5.3 | |
| WP8 Recovery tests | 3 | 5 | 9 | 5.3 | |
| WP9 Issues, RCA, report sections | 3 | 5 | 8 | 5.2 | |
| WP10 Viva preparation | 2 | 3 | 5 | 3.2 | |
| **Total** | | | | **≈ 54 h** (SD ≈ 3.3 h; 95 % range ≈ 47–61 h) | |

**Order of work.** The deadline isn't known yet; spread this over several days so the commit history shows real progress.
1. WP1 → WP2 (agree the overlap changes with the team) →
2. WP3 + WP4 (the use cases are the foundation for everything else) →
3. WP8, which can run in parallel because it's pure pytest →
4. WP5 baseline → WP6 (ZAP reuses the finished Playwright suite) → WP5 fix and rerun →
5. WP7 (after the suite is stable; a quiet machine is needed) →
6. WP9 → WP10.

---

## 13. Deliverables, file layout and commits (all under my own Git identity)

```
sqe/use-cases/UC-05.md, UC-06.md
sqe/member3/tool-versions.md, a11y-findings.md, security-assessment.md,
            access-matrix-results.md, performance-report.md, recovery.md
sqe/evidence/member3/{a11y/before,a11y/after,zap,audit,perf,playwright}/   (sanitized, no tokens or passwords)
sqe/windows_perf_settings.py
src/tests/team/e2e/rules.js, uc05-uc06.spec.js, usability.spec.js, a11y.spec.js, access.spec.js
src/tests/team/e2e/tools/lighthouse.mjs, merge-a11y.mjs
src/tests/team/perf/order-read.k6.js
src/tests/team/recovery/test_recovery.py
```

**Evidence hygiene:** `local/sqe/evidence` is git-ignored, but the brief requires the reports in the submission. Copy **sanitized** reports into `sqe/evidence/member3/`. Never commit `fixtures.json`, tokens, or raw traces that contain the Authorization header.

**Planned commits** on branch `sqe/browser-quality`, small and spread over real working days:
1. `test(sqe): add Member 3 fixtures for exceptional payments and keyboard cancellation`
2. `docs(sqe): specify UC-05 and UC-06 use cases`
3. `test(e2e): cover UC-05 exceptional payments`
4. `test(e2e): cover UC-06 keyboard cancellation and usability tasks`
5. `test(sqe): verify manager and viewer access decisions`
6. `test(sqe): add axe and Lighthouse accessibility scans with baseline reports`
7. `fix(control): <the chosen screen fix>` + `docs(sqe): accessibility before/after comparison`
8. `docs(sqe): ZAP passive scan, control review and dependency audit`
9. `test(sqe): add failure-and-recovery tests for cancellation and payment`
10. `test(perf): add k6 order-read workload and results`

Open the PR to `master`. Ask Tawassul to add `access.spec.js`, the a11y scan and `test_recovery.py` to the CI workflow.

---

## 14. Viva and live-task readiness

**Questions I must be able to answer without notes:**
- Why p95 and not the average?
- Why do my limits differ between 1 and 5 VUs?
- What does "unexpected failure" mean in my script?
- Why does Chromium need `--proxy-bypass-list=<-loopback>`?
- Lighthouse vs axe: why are their findings the same issues counted once?
- Why does ZAP flag the cookie, and why does the source show it's scheme-dependent?
- Why is hiding a link not access control (AC-04 vs UC-02 exc 1)?
- In REC-01, why do both failure points roll back completely (F8)? What does REC-02 show about the two transactions in `confirm` (F7)?
- Which UC-05/06 flows are EP, which are BVA, and which are state transitions?

**Live-task rehearsal.** Example: *"the fee cap changes from 100% to 50% of the total"*.
- Predicted failures: UC-06 exc 1 (19.99 would now be rejected), the UC-06 BVA values, Member 2's API BVA tests, and Tawassul's BR-03 unit and mutation tests. The CI unit and E2E gates fail.
- Edits: change `rules.js` constants (one place) and the oracle values. I'll rehearse this once before the viva.

**AI-use record:** add a row to `sqe/ai-use.md` for this planning session (tool: Claude Code; purpose: plan Member 3 phases; output: this document; checks: every file and line reference opened and confirmed; hypotheses marked unverified). Keep the prompts.

---

## 15. Items to agree with the team (send to Tawassul and Member 2)

1. The UC-05/06 redefinitions in §4.1, to avoid duplicate counting.
2. I add `M3*` fixtures to `sqe/orders_fixtures.py` in my PR (and note the F12 caching gotcha for everyone).
3. **To Member 2:** hypothesis H3 (API `mark_paid` with quota exhausted leaves a confirmed payment). It's in your API area.
4. **To Tawassul:** CI must run my access, a11y and recovery tests. The F2 payment-form fix could be the team's documented fix PR. GitHub Issues need enabling on the fork.
5. Risk IDs R11–R18 to merge into the register, and the release criteria in §11.
6. Python version drift: the handoff uses 3.14, my machine 3.12, CI 3.14. Note it in R10.

---

### Change log
| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-23 | Initial plan from source review; hypotheses H1–H5 not yet executed |
