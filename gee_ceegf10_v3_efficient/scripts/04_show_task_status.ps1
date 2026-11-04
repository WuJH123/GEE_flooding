$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
Push-Location $PKG
try { & $PY -m ceeprodgee status
 if ($LASTEXITCODE -ne 0) {throw 'EE task status failed'}
} finally {Pop-Location}
