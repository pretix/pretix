# Project progress

Inspected on 22 November 2026 using native Windows PowerShell. This summary compares the phase plans, working tree and saved local evidence. Test suites were not rerun during this audit. Remote collaborator acceptance and live GitHub checks were not inspected.

## Completed work

- Assignment guides for all nine phases and the course brief are in `Documents/Phases`. The two teammates' commit instructions are in `Documents/04-teammate-commits.md`.
- Branch `sqe/setup` contains 11 commits authored by `tawassulAkbr` after upstream baseline `526a79c7d`, ending at `1b81e6ec5`. These commits cover the brief and planning documents; the implementation below is still uncommitted.
- Phase 1: Native Windows setup, build and runner implemented. Saved evidence records a clean Django system check and restart/readback verification.
- Phase 2: Seed/reset and verification implemented. Both saved verification runs matched all 14 synthetic orders, checked anonymous denial and viewer access, and completed payment then cancellation on the same order. Initial test basis, RTM, risks and effort estimates documented.
- Phase 3: White-box tests, decision/state tables, CFG and coverage evidence prepared. JUnit records **30 passed, zero failures/errors/skips**. Local SonarQube scans completed before and after importing coverage.
- Phase 5: Playwright infrastructure and UC-01/UC-02 implemented. Latest saved Chromium run records **10 passed** across the two use cases.
- Phase 8: Two custom targeted mutations detected, with **2/2 killed**. A Windows GitHub Actions workflow is implemented locally.
- Windows handoff and AI-use documentation prepared. Detailed results are in [handoff](../sqe/handoff.md) and [test basis](../sqe/test-basis.md); raw evidence is under ignored `local/sqe/evidence/`.

## Remaining and incomplete work

| Phase / owner | Open tasks |
| --- | --- |
| 1–2 / Tawassul and team | Confirm teammate access and handoff; agree release criteria and maintain actual effort, risks, RTM and issue tracking as tests expand. |
| 3 / Tawassul | Close coverage gaps and triage the SonarQube vulnerability alert. Current scoped whole-file coverage is 20.7% combined, 25.7% line and 6.7% branch. The assignment coverage target remains open. |
| 4 / Member 2 | OpenAPI contract, deterministic equivalence-partition/boundary generator, original and revised datasets demonstrating two constraint changes, API/integration tests, role/replay checks, stored-state readbacks and findings. |
| 5 / Member 2 | Implement and verify UC-03 retained-fee cancellation and UC-04 payment then cancellation on the same order. |
| 5 / Member 3 | Implement and verify UC-05 exceptional payments and UC-06 keyboard cancellation. |
| 5 / Tawassul and team | Triage missing inline feedback for invalid payment precision. Existing test checks pending state and unchanged persisted data; a product correction remains open. Integrate all six use cases. |
| 6 / Member 3 | Usability/keyboard task checks, Lighthouse and axe reports, one screen improvement with before/after verification, route/data inventory, four-decision role matrix, passive ZAP assessment and dependency audit. |
| 7 / Member 3 | Agree performance thresholds; implement k6 and collect four controlled Windows runs; implement failure/restore/retry recovery testing with duplicate-write checks. |
| 8 / Tawassul | Broad mutation campaign, analysis of at least 15 surviving mutants, before/after scores, integrated CI suites, reachable SonarQube scanning, enforced thresholds/branch checks and real blocked/fix PR evidence. The local default Sonar gate is OK; live assignment gates remain unverified. |
| 9 / Tawassul and team | Merge verified teammate work, run the full suite from a clean Windows checkout, finalize evidence and release decision, issue lifecycle and two major-defect root-cause analyses, Pareto/GQM reporting, actual effort, final PDF and ZIP with Git history, extracted-package reproduction and viva preparation. |

Teammate suites and final integration are still pending in this checkout. Tawassul can continue coverage, finding triage and broader mutation work before those suites arrive. Live CI still needs an actual run; the documented local browser run used an explicitly managed server after automatic cleanup stalled.

## Modified and untracked files

Before adding this summary: **9 modified tracked files, 16 untracked files, zero staged files**. No tracked deletions were reported.

- Modified: all nine numbered Markdown guides in `Documents/Phases/` (38 insertions, 88 deletions).
- Untracked workflow: `.github/workflows/sqe-orders.yml`.
- Untracked support files: `sqe/ai-use.md`, `sqe/handoff.md`, `sqe/mutation.py`, `sqe/orders_fixtures.py`, `sqe/sonar-project.properties`, `sqe/test-basis.md`, `sqe/windows.ps1`, `sqe/windows_settings.py`, `sqe/windows_unit_settings.py`.
- Untracked browser files: `src/tests/team/e2e/orders.js`, `package-lock.json`, `package.json`, `playwright.config.js`, `uc01-uc02.spec.js` (all in that directory).
- Untracked unit file: `src/tests/team/unit/test_orders_rules.py`.

This audit adds only `Documents/PROGRESS.md`, bringing the untracked total to 17. Existing changes are preserved. Git reported that the user-level ignore file was inaccessible; these counts reflect the status Git returned in this environment.

## Commit update — 22 November 2026

The counts and uncommitted status above describe the earlier audit snapshot. Following the request for multiple implementation commits, the work is grouped into five additional commits under the configured `tawassulAkbr` identity, preserving the original 11 commits (16 total after the upstream baseline).

- `07a9c4e79`: Native Windows runner, settings and synthetic fixtures.
- `bfa4f701c`: Orders unit tests and scoped SonarQube configuration.
- `bf3636b5c`: Chromium UC-01/UC-02 scenarios and dependencies.
- `8eb1eaf11`: Targeted mutation runner and Windows CI workflow.
- This documentation commit: Updated phase guides, handoff, test basis, AI-use record and progress summary.

Pre-commit checks passed for Python lint using `src/setup.cfg`, JavaScript syntax, PowerShell parsing and tracked diff whitespace. Functional test counts above remain from the saved runs; suites were not rerun for committing. These commits are local; publishing and live CI verification remain pending.

When the lecture PDF folder is supplied, cross-check each phase and the final submission checklist against it. Review teammate contributions when requested. Neither review has been completed yet.
