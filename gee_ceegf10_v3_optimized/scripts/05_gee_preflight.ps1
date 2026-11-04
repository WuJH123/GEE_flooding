param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $PY)){throw "Python missing: $PY"}
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m pytest -q tests tests_legacy
if ($LASTEXITCODE -ne 0){throw 'GEE production source tests failed'}
& $PY -m ceeopt doctor --site gee
if ($LASTEXITCODE -ne 0){throw 'Original independent GEE project or GF10 source invalid'}
& $PY -m ceeopt cost
& $PY -m ceeopt gee-probe
if ($LASTEXITCODE -ne 0){throw 'Official GEE source band probe failed'}
Write-Host 'GEE_PREFLIGHT_OK: NO tasks have been submitted by this script.'
