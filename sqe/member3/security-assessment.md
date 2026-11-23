# Defensive security assessment — Orders W1 (manual payment) and W2 (cancellation)

Author: Member 3 · Date: 23 Nov 2026 · Target: team's local pretix copy at `http://127.0.0.1:18081` (baseline `526a79c7d`, synthetic data, test accounts only).
Method: passive inspection, source review and normal application actions. **No active scanning or attack payloads were used** — ZAP ran in *safe* mode as a passive proxy only.

Tools: Playwright 1.65.1 + Chromium 159, OWASP ZAP 2.17.0 (Temurin JRE 21.0.13.1), pip-audit 2.10.1, npm 11.16.0 `npm audit`. Raw evidence: `sqe/evidence/member3/security/` and `sqe/evidence/member3/audit/`.

## 1. Attack surface — routes and data in both workflows

| Route | Method | Authentication / control | Workflow | Data |
|---|---|---|---|---|
| `/control/login` | GET, POST | none → session cookie `pretix_session`, CSRF cookie `pretix_csrftoken` | both | e-mail, password |
| `/control/login/bad_origin` | POST | none, CSRF-exempt, `Access-Control-Allow-Origin: *` (anti-phishing beacon) | both (login) | page origin seen by JavaScript |
| `/control/event/{org}/{event}/orders/{code}/` | GET | session + `event.orders:read` | both | order, positions, payments, fees, customer e-mail |
| `…/orders/{code}/transition?status=p` | GET, POST | session + CSRF + `event.orders:write` | W1 | amount, payment_date, send_email, force |
| `…/orders/{code}/transition?status=c` | GET, POST | session + CSRF + `event.orders:write` | W2 | cancellation_fee, send_email, comment |
| `…/orders/{code}/refund` | GET | session + write | W2 (refund prompt, not executed) | amounts |
| `/api/v1/organizers/{org}/events/{event}/orders/{code}/` | GET | `Authorization: Token …` + `event.orders:read` | both | full order JSON incl. e-mail |
| `…/orders/{code}/mark_paid/` | POST | Token + `event.orders:write` | W1 | send_email |
| `…/orders/{code}/mark_canceled/` | POST | Token + `event.orders:write` | W2 | send_email, comment, cancellation_fee |

Roles: **Orders Manager** (team with `event.orders:read` + `event.orders:write`), **Orders Viewer** (`event.orders:read`), plus **anonymous**. Enforcement points in source: `control/views/orders.py:1452` (`OrderTransition.permission = 'event.orders:write'`), `control/permissions.py:82` (`EventPermissionRequiredMixin`), `api/views/order.py:341-342` (`permission` / `write_permission`), `api/auth/permission.py:57` (non-safe methods require `write_permission`).

## 2. Access matrix — automated with Playwright (`src/tests/team/e2e/access.spec.js`)

Run on fresh fixtures through the ZAP proxy: **13/13 decisions as expected, 0 unauthorized writes.** Denied actions are sent *directly* (not just "button hidden") and the order is read back afterwards.

| ID | Role | Action | Expected | Observed | Evidence |
|---|---|---|---|---|---|
| AC-01 | Manager | UI POST payment (M3S05) | allowed | allowed | HTTP 302, status n→p |
| AC-02 | Manager | UI POST cancel (M3S06) | allowed | allowed | HTTP 302, status p→c |
| AC-03 | Viewer | GET order detail | allowed | allowed | HTTP 200 |
| AC-08 | Viewer | API GET order | allowed | allowed | HTTP 200 |
| AC-04 | Viewer | GET payment form directly | denied | denied | HTTP 403 "Permission denied", order unchanged |
| AC-05 | Viewer | POST payment **with valid CSRF token** | denied | denied | HTTP 403 "Permission denied" (not the CSRF page), unchanged |
| AC-06 | Viewer | GET cancel form directly | denied | denied | HTTP 403 "Permission denied", unchanged |
| AC-07 | Viewer | POST cancel **with valid CSRF token** | denied | denied | HTTP 403 "Permission denied", unchanged |
| AC-09 | Viewer | API POST `mark_paid/` | denied | denied | HTTP 403 "You do not have permission to perform this action.", unchanged |
| AC-10 | Viewer | API POST `mark_canceled/` | denied | denied | HTTP 403 same message, unchanged |
| AC-11 | Anonymous | GET order detail | denied | denied | HTTP 302 → `/control/login?next=…` |
| AC-12 | Anonymous | API GET order | denied | denied | HTTP 401 |
| SEC-C3 | Manager | POST cancel **without** CSRF token | denied | denied | HTTP 403 "Verification failed" (CSRF page), unchanged |

Why AC-05/07 matter: the manager's identical request (AC-01/02, same CSRF mechanism) succeeds, and the viewer's response is the *Permission denied* page, not the *Verification failed* CSRF page. That isolates the server-side role check as the control that blocked the write.

## 3. Security controls reviewed

| ID | Control | Observation | Corroboration in source/config | Verdict |
|---|---|---|---|---|
| C1 | Session cookie attributes | `pretix_session`: HttpOnly ✔, Secure ✘, no SameSite attribute on our http instance (Chromium applies Lax by default). `pretix_csrftoken`: HttpOnly ✘. | `settings.py:458` `SESSION_COOKIE_HTTPONLY = True`; `helpers/cookies.py:29-50` returns early on http and on https sets `Secure`, `SameSite=None` and `Partitioned` (needed for the embeddable widget); `multidomain/middlewares.py:184-233` adds the `__Host-` prefix on https. Django's CSRF cookie is readable by design. | Verified. Missing Secure/SameSite is **environment-dependent** (http loopback). |
| C2 | Server-side role enforcement | 13/13 decisions correct over UI and API (section 2). | see section 1 enforcement points | Verified |
| C3 | CSRF protection on state-changing UI POSTs | Token-less POST → 403 *Verification failed*, order unchanged. | `multidomain.middlewares.CsrfViewMiddleware` in `settings.py` MIDDLEWARE; `{% csrf_token %}` in `pay.html` / `cancel.html`; `CSRF_FAILURE_VIEW` → `base/views/errors.py:37` | Verified |
| C4 | Security headers | `X-Frame-Options: DENY` and a CSP on normal responses ✔; CSP missing on 4xx/redirect responses; `X-Content-Type-Options` missing; `Server: WSGIServer/0.2 CPython/3.12.10`. | `settings.py:574`; `base/middleware.py` SecurityMiddleware skips CSP **only when `DEBUG` and status ≥ 400**; `deployment/docker/nginx.conf:14,27` sets `server_tokens off` and `X-Content-Type-Options nosniff` at the reverse proxy. | Verified; gaps are environment-dependent (DEBUG dev server without the reference nginx). |

## 4. ZAP passive scan — triage

ZAP 2.17.0 observed **2,419 messages** while Playwright ran UC-01/02, UC-05/06 and the access suite (38 tests). 787 alert instances in 15 alert types:

| Risk | Alert (plugin) | Instances | Where | Triage | Reason |
|---|---|---|---|---|---|
| High / Medium | Vulnerable JS Library (10003) | 1 + 1 | `/static/bootstrap/js/bootstrap.js` (Bootstrap 3.4.1, CVE-2025-1647); `/static/moment/moment-with-locales.js` (moment 2.29.1, CVE-2022-31129, CVE-2022-24785) | **True positive → finding SEC-F1** | Vendored libraries in `src/pretix/static/`. CVE-2022-24785 only affects server-side Node locale loading (not reachable in the browser). |
| Medium | Absence of Anti-CSRF Tokens (10202) | 52 | `<form method="dialog" class="modal-card-inner">` on order pages | **False positive** | `method="dialog"` forms close a client-side modal and are never submitted to the server; every real POST form carries `csrfmiddlewaretoken` (C3). |
| Medium | CSP: Failure to Define Directive with No Fallback (10055) | 70 | all control pages | **True positive (low) → SEC-F2** | `frame-ancestors` is covered by `X-Frame-Options: DENY`; `form-action` is not restricted. |
| Medium | CSP Header Not Set (10038) | 6 | 403/405 responses and one 302 on `…/transition` | **Environment-dependent** | Middleware intentionally omits CSP for error pages when `DEBUG=True`. |
| Medium | Cross-Domain Misconfiguration (10098) | 1 | `/control/login/bad_origin` `ACAO: *` | **False positive (by design)** | Anti-phishing beacon: returns an empty body; a cloned login page must be able to report. — But see **D-05** below. |
| Low | X-Content-Type-Options Header Missing (10021) | 132 | static files, control pages, API | **Environment-dependent → SEC-F3 (defence in depth)** | Set by the reference nginx, not by the application. |
| Low | Server Leaks Version Information (10036) | 160 | all | **Environment-dependent** | Django development server; production uses `server_tokens off`. |
| Low | Cookie without SameSite Attribute (10054) | 123 | `pretix_session`, `pretix_csrftoken` | **Environment-dependent** | See C1. |
| Low | Cookie No HttpOnly Flag (10010) | 50 | `pretix_csrftoken` | **False positive** | CSRF cookie must be readable; it carries no session authority. |
| Info | Authentication/Session Management Response Identified, Modern Web App, Suspicious Comments, User Controllable HTML Attribute | 191 | various | Informational | No exploitable behaviour observed; Django templates auto-escape reflected values. |

## 5. Dependency audit

| Ecosystem | Tool | Scope checked | Result |
|---|---|---|---|
| Python | pip-audit 2.10.1 (`--path local/sqe/venv/Lib/site-packages`) | 194 installed distributions (list in `audit/pip-freeze.txt`; `pretix` itself skipped as not on PyPI) | **3 advisories in 1 package**: `oauthlib 3.3.1` — PYSEC-2026-4114 / CVE-2026-49265 (timing side channel in PKCE `plain` comparison, fix 4.0.0) and CVE-2026-49272 / GHSA-3jp2-3mrg-2vxc (device-code grant issues bearer token for a bogus `device_code`, fix 4.0.1) |
| JavaScript (build) | `npm audit` (root `package.json`, 327 packages) | Vite/eslint/stylus build toolchain | 11 moderate — all in **devDependencies** (`eslint`, `typescript-eslint`, `stylus` → `glob` GHSA-3g3m-2fjr-6pw4, `minimatch` GHSA-g3hv-75wg-m249). Not shipped to the browser or the server. |
| JavaScript (tests) | `npm audit` (`src/tests/team/e2e`) | Playwright, axe-core, Lighthouse | 0 |

Reachability of the oauthlib advisories: the Orders workflows authenticate with team API tokens and sessions, not OAuth. pretix exposes OAuth2 for third-party apps with `PKCE_REQUIRED: False` (`settings.py:900`) and does not configure the device authorization grant. `pyproject.toml:70` pins `oauthlib==3.3.*`, so the fix needs an upstream dependency bump.

## 6. Findings (each linked to the risk register)

| ID | Finding | Root cause | Severity | Risk | Recommended correction |
|---|---|---|---|---|---|
| **D-05** | The anti-phishing origin check logs **every login as a possible phishing attempt** when pretix runs on a non-default port (68 false warnings in one run). Real reports would drown in noise. | `control/views/auth.py:170` builds `good_origin` from `scheme + '://' + hostname`, dropping the port that the browser includes in `location.origin`. Same comparison in the login-submission check. | Minor (operational security) | R21 (new: security monitoring degraded by false alarms) | Compare against `scheme + '://' + netloc` (or `urlsplit(SITE_URL)._replace(path='').geturl()`); add a unit test for a SITE_URL with an explicit port. |
| SEC-F1 | Vendored Bootstrap 3.4.1 and moment 2.29.1 have published CVEs. | Static copies in `src/pretix/static/` are not tracked by a package manager, so `npm audit` cannot see them. | Low (no exploit path found in W1/W2 pages) | R19 (new: outdated client libraries) | Upgrade moment to ≥ 2.29.4; track Bootstrap 3 (EOL) for a supported fork or migration; add the vendored files to an SBOM-based scan. |
| SEC-F2 | CSP has no `form-action`. | `_build_csp` defines `default-src`-based directives only. | Low | R19 | Add `form-action 'self'` (and `frame-ancestors 'none'` to mirror X-Frame-Options). |
| SEC-F3 | `X-Content-Type-Options: nosniff` relies on the reverse proxy. | App middleware never sets it; only `deployment/docker/nginx.conf:27` does. | Low (environment-dependent) | R18 (cookie/header protections depend on the deployment) | Also set it in `pretix.base.middleware.SecurityMiddleware` (defence in depth for non-reference deployments). |
| SEC-F4 | `oauthlib 3.3.1` advisories (PKCE timing, device-code token issuance). | Upstream pin `oauthlib==3.3.*`. | Low for W1/W2 (not reachable); medium for deployments that enable OAuth device flow | R20 (new: vulnerable dependency) | Bump to `oauthlib>=4.0.1` together with a compatible `django-oauth-toolkit`; keep `PKCE_REQUIRED` and avoid the `plain` challenge method. |

Verified controls with **no finding**: server-side role checks (C2), CSRF protection (C3), session cookie HttpOnly (C1), clickjacking protection via `X-Frame-Options: DENY` (C4).
