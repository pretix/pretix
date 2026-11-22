# Phase 9 — Clean-run E2E, final evidence and submission

[Phase list](01-windows-setup.md#phase-files) · [Previous phase](08-mutation-and-ci.md)

Tawassul leads the integrated clean run and assembles the submission. Each author provides their commit SHAs, PR or report links and observed results. Use the documented Windows PowerShell, Docker Desktop and fixture commands in `sqe/handoff.md`. [Teammate commits](../04-teammate-commits.md)

**Evidence.** Clean-start verification, a release or hold decision, one course PDF and one repository ZIP with history.

1. After the team PRs have passed the gates and merged, record the submission SHA. Reproduce the project from a clean Windows checkout of that commit. Reset the dedicated test data and run the full team suite, including all six browser use cases and Member 2's UC-04 W1 → W2 journey. Read the same order at the start and after both actions. Record the command, build and browser versions, actual pass/fail/skip counts, report path, and any deviations. Preserve the first run evidence if a fix and rerun are needed. [Playwright commands and evidence](05-playwright-use-cases.md#run-on-windows-and-record-evidence)
2. Reconcile the RTM, risk register, issue list and evidence index. Finalize GitHub Issues triage, severity, priority and lifecycle. Complete 5 Whys and fishbone analysis for at least two observed major defects, with corrective and preventive actions and a Pareto chart by category. Record evidence gaps accurately. Report scope tested, remaining areas, open defects, residual risk, estimates versus actual effort, weekly GQM and control actions. Compare actual results with each of the three or more release criteria and justify release or hold.
3. Include scope, provenance, test-management documents, test outcomes, ownership and commits, AI-use record, and evidence links in the PDF. For API, accessibility, security and performance findings, include root cause, severity, linked risk and fix. Include the public GitHub link, tool versions, baseline commit, setup and reset instructions, runnable scripts and data, CI configuration, and links to both PRs.
4. Package `Project_RollNumber1_RollNumber2_RollNumber3_Section.pdf` and the matching `.zip`. A pair omits the third roll number. Use a ZIP tool that includes `.git`, then inspect the archive and verify reproduction from an extracted copy. Check for secrets and real records before submission.
5. Verify the report's ownership against the authored commits and evidence links. Record any unfinished work or verification gaps in the completion report. The assignment's individual viva requirements remain in the course brief. [Assignment §6](SQE_Final_Project%20Fall%202026.pdf)

## Rubric cross-check

| Assignment section | Phase evidence |
|---|---|
| §1 system, scope and baseline | 1–2 |
| §2 plan, risk, RTM, reporting and defects | 2 and 9, updated throughout |
| §2 SonarQube, CFG and white-box | 3 |
| §2 API, integration and data generator | 4 |
| §2 browser use-case specification and automation | 5 and clean rerun in 9 |
| §2 mutation and CI quality gates | 8 |
| §3 usability/accessibility | 6 |
| §4 defensive security | 6 |
| §5 performance/recovery | 7 |
| §6 submission and viva, §7 AI use | 9 and ongoing disclosure |

### Source references

- [Course brief, pages 1–7](SQE_Final_Project%20Fall%202026.pdf).
- [Pinned development instructions](../../doc/development/setup.rst), [Dockerfile](../../Dockerfile), [container entrypoint](../../deployment/docker/pretix.bash), and [Python metadata](../../pyproject.toml).
- [REST order actions](../../src/pretix/api/views/order.py), [control panel views](../../src/pretix/control/views/orders.py), and [order forms](../../src/pretix/control/forms/orders.py).
- [Order models and payment logic](../../src/pretix/base/models/orders.py) and [cancellation service](../../src/pretix/base/services/orders.py).
