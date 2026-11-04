param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $PY)){throw "Python missing: $PY"}
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m pytest -q tests
if ($LASTEXITCODE -ne 0){throw 'Offline native WorldCover tests failed'}
& $PY -m ceeopt doctor --site server --root $Root
if ($LASTEXITCODE -ne 0){throw 'Frozen GF10 global register invalid'}
Write-Host 'SERVER_PREFLIGHT_OK (no GEE tasks)' -ForegroundColor Green
