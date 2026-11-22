# Phase 1 — Verify your clone, pin and boot

[Next phase](02-seed-reset-and-test-planning.md)

Open `D:\pretix` in Windows PowerShell. Run Docker Desktop in Linux container mode through its existing `docker-desktop` WSL 2 distribution. Project commands run from PowerShell, and pretix runs inside Docker.

Use the team fork `tawassulAkbr/pretix` throughout. Each phase lists the work and evidence the team needs to produce. [Course brief](SQE_Final_Project%20Fall%202026.pdf)

**Evidence.** `sqe/baseline.md`, PowerShell reproduction commands, local smoke results, and the handoff to Phase 2. The exit checks are an agreed Git baseline, control panel login, authenticated synthetic API read, and persistence after restart.

## Verify Git, Docker and storage

1. Tawassul coordinates registration in the section's shared sheet within five days of the announcement if the entry is available. Record the actual registration status. Verify `sqe/setup`, the baseline SHA, `origin` pointing to upstream, and `team` pointing to `tawassulAkbr/pretix`. Use the fork's `master` as the planned integration branch. Tawassul prepares the setup changes on `sqe/setup` and brings them into the fork. Confirm the teammates can access the fork and its integration branch before they create their work branches. Record the baseline SHA separately from the integration branch's current SHA. [Team ownership and handoffs](#execution-and-handoff-convention)
2. Check Docker Desktop's engine, data location and free space before building. `/var/lib/docker` is the engine's path inside Linux. Check the Windows drive in **Docker Desktop → Settings → Resources → Advanced**. On this machine the WSL data VHD was observed under `%LOCALAPPDATA%\Docker\wsl\disk`. Recheck the Windows disk location and free space when you run the phase. The checkout is on `D:`.

```powershell
Set-Location D:\pretix
git status --short --branch
git remote -v
git rev-parse HEAD
wsl.exe --list --verbose
docker context show
docker info --format '{{.OSType}} | {{.ServerVersion}} | {{.DockerRootDir}}'
docker system df
[System.IO.DriveInfo]::new('C:\').AvailableFreeSpace / 1GB
[System.IO.DriveInfo]::new('D:\').AvailableFreeSpace / 1GB
Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Docker\wsl" -Recurse -File -Filter '*.vhdx'
```

## Build or reuse the pinned image

Review the [Dockerfile](../../Dockerfile), [build exclusions](../../.dockerignore) and [entrypoint](../../deployment/docker/pretix.bash). If `pretix-sqe:526a79c` is already present, verify its build provenance and record its image ID. For a fresh build, archive the exact commit with LF line endings. The Windows working tree can contain CRLF, which previously caused Linux to look for `python3\r`. The archive also preserves the committed executable bit. `cmd.exe` carries the binary tar stream between Git and Docker when this command is launched from PowerShell.

```powershell
$baseline = '526a79c7d175a37421242a8167821373c357773d'
cmd.exe /d /c "git -c core.autocrlf=false -c core.eol=lf archive --format=tar $baseline | docker build --progress=plain -t pretix-sqe:526a79c -"
if ($LASTEXITCODE -ne 0) { throw 'The Docker build failed. Check the first failing build step.' }
docker image inspect pretix-sqe:526a79c --format '{{.Id}} {{json .Config.Entrypoint}} {{json .Config.Cmd}}'
```

This archive contains the baseline commit. Record the exact source used later for team tests and PR builds, including changes made after the baseline.

## Start and verify the local application

Use the entrypoint's `web` mode with SQLite for the smoke setup. It runs migrations and starts nginx and Gunicorn. Use a named volume for `/data`, including the SQLite database, and publish container port 80 to Windows loopback only. If `pretix-sqe-phase1` already exists, inspect its port and mounts and use `docker start pretix-sqe-phase1` if it is stopped. For a new container, run the following from PowerShell.

```powershell
docker run -d --name pretix-sqe-phase1 `
  --publish 127.0.0.1:18080:80 `
  --mount type=volume,source=pretix-sqe-phase1-data,target=/data `
  --env PRETIX_PRETIX_URL=http://127.0.0.1:18080 `
  --env PRETIX_PRETIX_INSTANCE_NAME=pretix-sqe `
  --env PRETIX_PRETIX_ECB_RATES=false `
  --env PRETIX_PRETIX_PASSWORD_RESET=false `
  --env PRETIX_DATABASE_BACKEND=sqlite3 `
  --env NUM_WORKERS=1 pretix-sqe:526a79c web
docker logs --tail 30 pretix-sqe-phase1
docker port pretix-sqe-phase1
docker volume inspect pretix-sqe-phase1-data
```

1. Wait for migrations to finish. Open `http://127.0.0.1:18080/control/` in a Windows browser and verify login, the dashboard, and static assets. For a fresh instance, rotate the bootstrap password and obtain a read-scope token for a synthetic organizer. Keep secrets in an ignored `local/` directory or another private location.
2. Use PowerShell or a local API client to read the synthetic organizer with `Authorization: Token <local token>`. Record the anonymous status, the authenticated status, and the returned organizer identity without capturing the token. The existing smoke instance used `GET /api/v1/organizers/sqe-smoke/`.
3. Run `docker restart pretix-sqe-phase1`. Wait for readiness, then repeat the API read with the same token and verify that the organizer is still present. Record the database backend, volume, port, image ID, Docker version, Windows browser version, and container Python, Django and Node versions. Log the build warnings and any unresolved checks in the baseline and handoff.

To reproduce the authenticated read for the existing smoke fixture from PowerShell, use the ignored token file. Record the status and organizer identity rather than the request headers.

```powershell
$uri = 'http://127.0.0.1:18080/api/v1/organizers/sqe-smoke/'
$token = (Get-Content -LiteralPath .\local\sqe\phase1-api-token.txt -Raw).Trim()
try {
    $reply = Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers @{ Authorization = "Token $token" }
    $reply.StatusCode
    $reply.Content | ConvertFrom-Json | Select-Object slug,name
} finally {
    Remove-Variable token
}
```

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

Put course artifacts in `sqe/` and student-authored tests in `src/tests/team/`. Launch Django and pytest work from PowerShell in Linux containers. Run scoped pytest from the container's `src/` working directory to use the pinned test configuration. Use a dedicated test container with the dev dependencies and test database. Run Playwright Chromium against the published loopback URL from Windows and record how CI reaches its test instance. Use the same database configuration for comparable functional runs.

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
