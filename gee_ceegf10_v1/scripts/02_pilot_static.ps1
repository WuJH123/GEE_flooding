$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
& $PY -m ceegee pilot-static --cells 16
if ($LASTEXITCODE -ne 0) { throw 'Pilot submission failed, no full exports submitted' }
Write-Host 'FOUR SMALL PILOTS SUBMITTED; use 03_collect_and_check.ps1 after they finish.'
