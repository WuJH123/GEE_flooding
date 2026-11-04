$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
if (!(Test-Path $PY)) {
  $BOOT = 'E:\GEE_flooding\.venv\Scripts\python.exe'
  if (Test-Path $BOOT) { & $BOOT -m venv (Join-Path $PKG '.venv') }
  else { & py -3 -m venv (Join-Path $PKG '.venv') }
  if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed' }
}
& $PY -m pip install -r (Join-Path $PKG 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
Push-Location $PKG
try {
  & $PY -m pytest tests -q
  if ($LASTEXITCODE -ne 0) { throw 'Offline test failure - no EE jobs allowed' }
  & $PY -m ceeprodgee configure --root 'E:\GEE_flooding'
  & $PY -m ceeprodgee verify
  if ($LASTEXITCODE -ne 0) { throw 'Frozen GF10 check failed' }
} finally { Pop-Location }
