# Windows SQE handoff

The pretix source baseline is 526a79c7d175a37421242a8167821373c357773d. The initial Windows runs started from the sqe/setup checkout at 1b81e6ec5fd7c5fd68d46abd97de8f8a35694762 with the working-copy SQE harness and tests. Record the tested commit and any working-copy changes for subsequent runs. The team fork is tawassulAkbr/pretix. [Phase guides](../Documents/Phases/01-windows-setup.md#phase-files) · [Test basis](test-basis.md)

## Prepare the Windows checkout

Run from the repository root in PowerShell. Use an installed native Windows CPython, uv, and Node. The workstation has CPython 3.14.6 at D:\Python\python.exe, Django 5.2.19, Node 26.4.0, npm 11.17.0 and pytest 9.2.0. The repository's .node-version specifies Node 24 for CI.

~~~powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'local\sqe\uv-cache'
$env:npm_config_cache = Join-Path (Get-Location) 'local\sqe\npm-cache'
uv venv .\local\sqe\venv --python D:\Python\python.exe
uv pip install --python .\local\sqe\venv\Scripts\python.exe -e '.[dev]'
npm.cmd ci --no-audit --no-fund
npm.cmd run build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 check
~~~

Use the path to your CPython executable on each Windows machine. The core Vite control and widget build completed. The build emitted an optional plugin discovery warning while configuring Vite and a widget output-directory warning. The Orders fixtures use pretix core features.

## Reset and verify the fixtures

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 reset
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 verify
~~~

Reset creates and migrates a candidate SQLite database, seeds it, then replaces the disposable database at local/sqe/windows/orders.sqlite3. Stop the test server before resetting. The verify command checks the starting fixture contract and then changes SQE02 from pending to paid to canceled. Reset again before a new run. Keep credentials, database files, logs and traces in the ignored local directory.

| Setting | Value |
| --- | --- |
| App and role login | http://127.0.0.1:18081/control/login |
| Organizer and event | sqe-orders / orders |
| Currency, language and time zone | EUR, English, UTC |
| Accounts and tokens | The roles.manager and roles.viewer entries in local/sqe/windows/fixtures.json |
| API readback | GET /api/v1/organizers/sqe-orders/events/orders/orders/{code}/ with Authorization: Token followed by the viewer token |
| Fixture aliases | The orders entries in the local JSON file and the ORDERS mapping in the fixture script |

The paid orders contain a confirmed manual payment. The limited item has one place held by SQE04, so PAY05 cannot reacquire quota. Reserve SQE02 for the verification journey and reset it before reusing it. Choose fresh aliases for additional member tests and agree their starting state before adding them to shared runs. [Fixture implementation](orders_fixtures.py)

## Run the white-box, mutation and browser checks

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 unit
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 mutation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sqe\windows.ps1 reset
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) 'local\sqe\browsers'
Push-Location .\src\tests\team\e2e
npm.cmd ci --no-audit --no-fund
npm.cmd exec -- playwright install chromium --only-shell
npm.cmd test
Pop-Location
~~~

Playwright starts and stops the loopback test server. To start that server separately for manual checks or the API suite, run the Windows script with serve. The coverage, JUnit, browser results and HTML report are written below local/sqe/evidence. Keep raw Playwright failure traces private because they can contain test credentials and authorization headers. Share sanitized results.

For an already-running SQE instance, set SQE_REUSE_SERVER to 1 before npm.cmd test in the browser project. Stop the instance yourself after the run. The workstation verification used this mode after Playwright's process cleanup stalled in the sandbox. The verified Windows browser run used Playwright 1.65.1 and Chromium 159.0.8154.6.

## Run SonarQube on Windows

The scoped scan uses five upstream Orders source files and the team unit test directory. SonarQube Community Build 26.11.0.134175 ran on loopback port 19000 with the embedded H2 database, Temurin JDK 21.0.13.1, and SonarScanner CLI 8.4.0.16527. The server requires the full JDK for Elasticsearch. Set SONAR_JAVA_PATH to its java.exe and set the scanner's SONAR_HOST_URL and SONAR_TOKEN in the PowerShell session. Keep the token in local configuration. [Windows server setup](https://docs.sonarsource.com/sonarqube-community-build/server-installation/from-zip-file/basic-installation) · [SonarScanner CLI](https://docs.sonarsource.com/sonarqube-community-build/analyzing-source-code/scanners/sonarscanner)

~~~powershell
sonar-scanner.bat -Dproject.settings=sqe/sonar-project.properties
sonar-scanner.bat -Dproject.settings=sqe/sonar-project.properties -Dsonar.python.coverage.reportPaths=local/sqe/evidence/coverage.xml
~~~

## Verification record

| Phase | Observed result | Local evidence |
| --- | --- | --- |
| 1 Windows baseline | Django system check passed with zero issues. On two starts, control login, the scoped API and a Vite asset each returned 200. The readback preserved SQE02's canceled state across restart. | phase1-check.log, phase1-restart.json |
| 2 Fixtures and planning | Two independent resets matched all 14 expected synthetic orders. Anonymous reads returned 401 and scoped viewer reads returned 200. SQE02 completed W1 → W2 on both passes with one EUR 20.00 confirmed payment and zero cancellation fees. | phase2-reset-1.log, phase2-reset-2.log, phase2-verify-1.log, phase2-verify-2.log |
| 3 Static analysis and white-box | 30 passed. SonarQube scanned the five Orders source files before and after importing coverage. The test basis records both results, procedure-level coverage and remaining gaps. | unit-first.xml, unit.xml, coverage.xml, coverage.json, phase3-sonar-initial.json, phase3-sonar-coverage.json |
| 4 API and generator | Member 2 can use the fixture readback and payment-to-cancellation journey above. | Pending teammate implementation |
| 5 Browser | 10 passed, 0 failed, 0 skipped after a fresh reset. UC-01 and UC-02 each ran a main flow, two alternatives and two exceptions. The prior runs captured locator failures and the missing invalid-payment feedback. | phase5-browser.log, playwright-report/index.html, playwright-first-results, playwright-revised-results |
| 6–7 Browser quality and performance | The loopback instance and scoped roles are available for Member 3. | Pending teammate implementation |
| 8 CI and mutation | Two targeted mutants were killed. The clean control ran 14 selected tests with 14 passes. The Windows PR workflow is present locally. The broad mutation campaign and live PR gate evidence are pending. | phase8-mutation.log, mutation-*.xml |
| 9 Integrated run | Starts after teammate PRs pass and merge. | Pending integration |
