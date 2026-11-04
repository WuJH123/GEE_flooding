$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
Push-Location $PKG
try { & $PY -m ceeprodgee submit --family merit --pilot --execute --confirm CEE_GF10_M1M2_PRODUCTION_20261104_V2
 if ($LASTEXITCODE -ne 0) { throw 'MERIT pilot submission failed' }
} finally {Pop-Location}
