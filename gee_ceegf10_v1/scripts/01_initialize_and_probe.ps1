$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
& $PY -m ceegee init
if ($LASTEXITCODE -ne 0) { throw 'Refusing to proceed: dedicated asset folder creation failed' }
& $PY -m ceegee source-probe
if ($LASTEXITCODE -ne 0) { throw 'Official GEE dataset band validation failed' }
