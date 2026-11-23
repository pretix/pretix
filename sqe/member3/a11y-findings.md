# Usability and accessibility evaluation — Orders control panel

Author: Member 3 · Date: 23 Nov 2026 · Tools: Playwright 1.65.1 + Chromium 159, `@axe-core/playwright` 4.14.0 (axe tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice`), Lighthouse 13.6.0 (accessibility, best practices, SEO; desktop preset, provided throttling, 3 runs per screen, median reported).
Evidence: `sqe/evidence/member3/a11y/{before,after}/` (raw axe JSON, Lighthouse HTML+JSON run 1, `summary.json` with all three runs, `merged-findings.{md,json}`) and `sqe/evidence/member3/playwright-report/` (sanitized).

## 1. Automated usability task tests

| ID | Workflow | What the test does | Result |
|---|---|---|---|
| USA-01 (= UC-05 main) | W1 payment | Opens the payment task screen, records 12.00 then the prefilled 8.00, asserts the confirmation "The payment has been created successfully." and the order status shown (Pending → Paid) plus the stored payments. | Pass |
| USA-02 (= UC-06 exc 1) | W2 cancellation | **Keyboard only.** Asserts the focus order *fee → Notify by email → Comment → No, take me back → Yes, cancel order*; unticks e-mail with Space; submits a fee of 20.01 with Enter; asserts the error *"The cancellation fee cannot be higher than the total amount of this order."* is shown in the field's `.has-error` group and the typed value is kept; corrects to 19.99 by keyboard; asserts success and the stored fee/total/positions. | Pass |

The error message tells the user what to correct (the limit is the order total). In contrast, the payment form gives **no** message for invalid input (known defect D-03, UC-05 exc 1c) and the date picker silently replaces an unparseable date with today's (observation U-01) — both are usability findings in section 4.

## 2. Screens and method

| Screen | URL (fixture) | Used by |
|---|---|---|
| S1 Order detail | `/control/event/sqe-orders/orders/orders/M3L02/` | every use case |
| S2 Mark as paid form | `…/orders/M3L01/transition?status=p` | UC-01, UC-05 (key screen W1) |
| S3 Cancel order form | `…/orders/M3L02/transition?status=c` | UC-02, UC-03, UC-06 (key screen W2) |

Lighthouse runs while logged in: Playwright logs in to a persistent Chromium profile exposed on a debugging port and Lighthouse audits that browser with `disableStorageReset` and the real User-Agent (pretix ends a session whose User-Agent changes). A guard aborts if Lighthouse is redirected to the login page.

**Counting once.** Lighthouse's accessibility audits are axe-core rules. `tools/merge-a11y.mjs` keys each issue on *(screen, rule, normalised opening tag of the element, occurrence)*, so an element reported by both tools counts once.

## 3. Results before and after the fix

| Screen | Lighthouse accessibility (median of 3) | Lighthouse best practices | Lighthouse SEO | axe violated rules | Unique issues (merged) |
|---|---|---|---|---|---|
| S1 Order detail | 79 → **92** | 100 → 100 | 50 → 58 | 9 → 3 | 28 → 7 |
| S2 Mark as paid | 78 → **100** | 100 → 100 | 50 → 58 | 8 → **0** | 15 → **0** |
| **S3 Cancel order (fixed screen)** | 78 → **100** | 100 → 100 | 50 → 58 | 8 → **0** | 16 → **0** |
| Total | | | | | **59 → 7** (31 of the 59 found by both tools) |

All three Lighthouse runs gave identical scores in both phases. The SEO rise from 50 to 58 comes from the SEO `image-alt` audit, fixed by A1; the remaining SEO failures (`is-crawlable`, `meta-description`) are intended for an admin backend. The fix was made in the shared control-panel layout used by S3, so S1 and S2 improved as a side effect; the remaining 7 issues are in content specific to S1.

## 4. Findings, prioritised (before the fix)

Priority = axe impact × how often the element is met in the two workflows (it is on every screen of both).

| # | Rule (WCAG) | Impact | Element | Screens | Found by | User impact | Fix | Status |
|---|---|---|---|---|---|---|---|---|
| A1 | `image-alt` (1.1.1) | critical | `.navbar-brand > img` (logo) | S1–S3 | both | Screen readers announce the image file name before the instance name on every page. | `alt=""`: the image is decorative, the visible instance name follows it. | **Fixed** |
| A2 | `html-has-lang` (3.1.1) | serious | `<html>` | S1–S3 | both | Screen readers guess the language and may mispronounce all page text; browser translation and hyphenation misbehave. | `lang="{{ LANGUAGE_CODE }}"` from the active locale. | **Fixed** |
| A3 | `link-name` (2.4.4, 4.1.2) | serious | sidebar `a.arrow[href="#"]` ×3 | S1–S3 | both | Keyboard and screen-reader users hear "link" with no name for the sub-menu toggles and cannot tell what they do. | `aria-label="Show or hide the {menu} sub-menu"`, icon `aria-hidden`. | **Fixed** |
| A4 | `color-contrast` (1.4.3) | serious | `.context-meta` (event date in the top bar) | S1–S3 | both | Low-vision users cannot read the event date (4.26:1 even at opacity 0.9; 4.5:1 needed for 11 px text). | Remove the 0.7 opacity so the text uses the full theme colour. | **Fixed** |
| A5 | `link-in-text-block` (1.4.1) | serious | footer "powered by pretix" link | S1–S3 | both | Users with colour-vision deficiency cannot see that the footer text contains a link. | Underline links inside the footer. | **Fixed** |
| A6 | `landmark-one-main` | moderate | page | S1–S3 | both | Screen-reader users cannot jump straight to the content with the "main" landmark shortcut. | `<div id="page-wrapper">` → `<main id="page-wrapper">` (CSS uses the id only). | **Fixed** |
| A7 | `region` | moderate | page heading, forms, buttons (25 elements) | S1–S3 | axe | Content outside landmarks is skipped when navigating by landmarks. | Resolved by A6. | **Fixed** |
| A8 | `landmark-unique` | moderate | two `role="navigation"` elements | S1–S3 | axe | Two unnamed "navigation" regions are indistinguishable. | `aria-label` "Top navigation" / "Sidebar navigation". | **Fixed** |
| A9 | `color-contrast` (1.4.3) | serious | panel-heading action links ("Edit", "Change") | S1 | both | Low-vision users may miss the edit actions on the order. | Darken the link colour on `.panel-default > .panel-heading` (theme variable). | Open (S1-specific) |
| A10 | `link-name` (2.4.4) | serious | icon-only buttons in the order details list (`dd > a.btn-xs`) | S1 | both | Icon buttons (e.g. copy/resend) have no accessible name. | Add `aria-label` or visually hidden text to each icon button. | Open (S1-specific) |
| A11 | `heading-order` | moderate | `h3.panel-title` after `h1` | S1 | both | Heading outline skips a level; navigating by headings is confusing. | Use `h2` for panel titles or adjust styles. | Open (S1-specific) |
| L1 | SEO `is-crawlable` | — | `<meta name="robots" content="noindex">` | S1–S3 | Lighthouse | None — the admin backend must not be indexed. | Keep (intended). | Accepted |
| L2 | SEO `meta-description` | — | page | S1–S3 | Lighthouse | None for a logged-in backend. | Not needed. | Accepted |
| L3 | best-practices `valid-source-maps` (audit weight 0, so best practices stays 100) | — | large first-party JS | S1–S3 | Lighthouse | Developer-only. | Optional. | Accepted |

A new issue appeared during the fix and was resolved before the final run: putting `role="main"` on a `div` made axe report the `<footer>` as a nested contentinfo landmark (`landmark-contentinfo-is-top-level`). Using a real `<main>` element removes the footer's landmark role.

Usability findings from the task tests (cross-referenced to the defect log):

| ID | Finding | Severity | Proposed fix |
|---|---|---|---|
| D-03 | Invalid input on the payment form (e.g. amount `abc`) redirects to the order with no message; the manager cannot tell that nothing was recorded or why. | Major (usability) | Re-render `pay.html` with form errors when `MarkPaidForm` is invalid, as the cancel branch already does (`OrderTransition.post`). |
| U-01 | Typing an unparseable payment date silently becomes today's date. | Minor | Show a validation message from the date picker instead of restoring the previous value, or disable silent correction. |

## 5. The fix (one screen: S3 Cancel order, via its layout)

Files changed (commit on `zubair/feature/accessibility`):
- `src/pretix/control/templates/pretixcontrol/base.html` — A1, A2, A3, A6, A8.
- `src/pretix/static/pretixcontrol/scss/_sb-admin-2.scss` — A4.
- `src/pretix/static/pretixcontrol/scss/main.scss` — A5.

Verification: axe "after" scan has no violations on S3 (the a11y test asserts no serious/critical violations for `A11Y_FIXED_SCREEN=S3-cancel-form`), Lighthouse accessibility 78 → 100 in all three runs, and the full browser regression suite (UC-01/02, UC-05/06, access matrix — 38 tests) still passes with the three known-defect expected failures.
