param(
    [Parameter(Mandatory)]
    [ValidateSet('check', 'reset', 'verify', 'serve', 'unit', 'mutation')]
    [string] $Action
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo 'local\sqe\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Create the Windows test virtual environment using sqe/handoff.md.'
}

$oldPythonPath = $env:PYTHONPATH
$oldSettings = $env:DJANGO_SETTINGS_MODULE
$oldConfig = $env:PRETIX_CONFIG_FILE
$env:PYTHONPATH = "$repo;$repo\src"
Push-Location (Join-Path $repo 'src')
try {
    if ($Action -in 'unit', 'mutation') {
        $env:DJANGO_SETTINGS_MODULE = 'sqe.windows_unit_settings'
        $env:PRETIX_CONFIG_FILE = 'tests/ci_sqlite.cfg'
        if ($Action -eq 'mutation') {
            & $python -m sqe.mutation
        } else {
            $evidence = Join-Path $repo 'local\sqe\evidence'
            New-Item -ItemType Directory -Force -Path $evidence | Out-Null
            & $python -m pytest tests/team/unit --cov=pretix --cov-branch "--cov-report=xml:$evidence\coverage.xml" "--junitxml=$evidence\unit.xml"
            if ($LASTEXITCODE -eq 0) {
                & $python -m coverage json -o "$evidence\coverage.json"
            }
        }
    } else {
        $env:DJANGO_SETTINGS_MODULE = 'sqe.windows_settings'
        switch ($Action) {
            'check'  { & $python manage.py check }
            'reset'  { & $python -m sqe.orders_fixtures reset }
            'verify' { & $python -m sqe.orders_fixtures verify }
            'serve'  { & $python manage.py runserver 127.0.0.1:18081 --noreload }
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "SQE $Action failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
    $env:PYTHONPATH = $oldPythonPath
    $env:DJANGO_SETTINGS_MODULE = $oldSettings
    $env:PRETIX_CONFIG_FILE = $oldConfig
}
