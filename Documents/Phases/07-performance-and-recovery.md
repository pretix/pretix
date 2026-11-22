# Phase 7 — Performance and recovery

[Phase list](01-windows-setup.md#phase-files) · [Previous phase](06-usability-accessibility-and-security.md) · [Next phase](08-mutation-and-ci.md)

Member 3 owns performance and recovery on `sqe/browser-quality`. Use the build, fixtures, W1/W2 workflows and RTM recorded in `sqe/handoff.md`. Run local checks from Windows PowerShell against the dedicated Docker Desktop test instance. [Teammate commits](../04-teammate-commits.md#member-3)

**Evidence.** k6 script, four raw workload runs, environment details, comparison against thresholds, and one automated failure, restore and retry result.

1. Measure authenticated order-detail GET, a read used by both workflows. Define and justify the p95 and unexpected failure thresholds for each workload before testing. Use `p95 ≤ 500 ms` and `< 1%` unexpected failures only as starting proposals for the chosen workstation.
2. Run k6 OSS from PowerShell against the dedicated Docker app's Windows loopback port. Run the same script twice at one virtual user and twice at five or more simultaneous virtual users. Measure at least 60 seconds after the target is reached in each run. Use the same Windows machine, Docker resource settings, build, starting data, and warmup. Avoid concurrent workloads. Validate response status and order identity, save p95 in milliseconds, completed requests per second and unexpected failure percentage, and compare the results with the thresholds.
3. Run the recovery test in the dedicated test container. Make a deterministic test double fail before a cancellation write completes. Read persisted order, positions, fees and counts afresh. Restore the dependency, retry, and assert the expected final state and absence of duplicate business records. Link results to the risks, causes and proposed corrections. Update the handoff for Phase 8.
4. Commit the k6 script, raw run evidence or links, recovery test, and Phase 6 defensive assessment notes. Give Tawassul the recovery command for CI and the observed load metrics for the final release decision. Keep the controlled Windows measurements traceable to their environment and limits.
