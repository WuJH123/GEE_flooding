$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
Write-Host 'METHOD TEST ONLY; 2023-06-01 is not a verified flood event.'
& $PY -m ceegee pilot-event --date 2023-06-01 --cells 12
if ($LASTEXITCODE -ne 0) { throw 'Event method test submission failed' }
