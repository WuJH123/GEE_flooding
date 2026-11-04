$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
Push-Location $PKG
try { & $PY -m ceeprodgee event-pilot --date 2023-06-01 --execute --confirm CEE_GF10_M1M2_PRODUCTION_20261104_V2
 if ($LASTEXITCODE -ne 0) {throw 'Event method pilot failed'}
} finally {Pop-Location}
