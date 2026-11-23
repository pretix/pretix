# Stop the SQE test server if it is listening, reset the fixture database, and report when the port is free.
# Member 3 helper: every mutating browser suite must start from freshly reset fixtures.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\sqe\m3-fresh-server.ps1
#        then start the server with: .\sqe\windows.ps1 serve   (or serve-perf for k6)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$listeners = Get-NetTCPConnection -LocalPort 18081 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
}
for ($i = 0; $i -lt 20 -and (Get-NetTCPConnection -LocalPort 18081 -State Listen -ErrorAction SilentlyContinue); $i++) {
    Start-Sleep -Milliseconds 500
}
if (Get-NetTCPConnection -LocalPort 18081 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 18081 is still in use; stop the SQE server before resetting.'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'sqe\windows.ps1') reset
if ($LASTEXITCODE -ne 0) { throw "Reset failed with exit code $LASTEXITCODE." }
Write-Output 'Fixtures reset; port 18081 is free.'
