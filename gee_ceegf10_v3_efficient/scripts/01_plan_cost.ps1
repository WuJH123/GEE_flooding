$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
Push-Location $PKG
try {
  & $PY -m ceeprodgee plan --family merit --scope all
  if ($LASTEXITCODE -ne 0) { throw 'MERIT plan failed' }
  & $PY -m ceeprodgee plan --family worldcover --scope all
  if ($LASTEXITCODE -ne 0) { throw 'WorldCover plan failed' }
  Write-Host 'PLANNING ONLY. The WorldCover global plan is NOT a submission authorization.'
} finally { Pop-Location }
