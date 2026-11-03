$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
& $PY -m ceegee tasks
if ($LASTEXITCODE -ne 0) { throw 'Task usage query failed' }
& $PY -m ceegee qa-pilot
if ($LASTEXITCODE -ne 0) { throw 'Pilot failed or still running; no full exports allowed' }
Write-Host 'PILOT_QA_PASS: manually inspect reports/pilot_qa.json and actual EECU consumption.'
