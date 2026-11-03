$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
# This only reads registered tasks. Add -cancel by explicit user intent.
& $PY -m ceegee guard-budget --max-task-hours 25 --max-run-hours 300
if ($LASTEXITCODE -ne 0) { throw 'CEE project task quota guard requires attention' }
