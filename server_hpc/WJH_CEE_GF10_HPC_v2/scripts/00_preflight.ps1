$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE'
$PKG=Split-Path -Parent $PSScriptRoot
$PY="$ROOT\.venv\Scripts\python.exe"
if (!(Test-Path $PY)) { throw 'Existing server Python environment absent: '+$PY }
if (!(Test-Path "$ROOT\gf10_global_nonantarctic_land.parquet")) { throw 'Original frozen GF10 missing' }
$env:PYTHONPATH=$PKG
$env:GDAL_NUM_THREADS='2'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
Set-Location $PKG
& $PY -m pip install -r "$PKG\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
& $PY -m pytest "$PKG\tests" -q
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed; do not run global job' }
& $PY -m gf10hpc --root $ROOT audit
if ($LASTEXITCODE -ne 0) { throw 'Frozen grid audit failed' }
& $PY -m gf10hpc --root $ROOT inventory
if ($LASTEXITCODE -ne 0) { throw 'Local downloaded inventory failed' }
& $PY -m gf10hpc --root $ROOT tiles --side 64 --out "$ROOT\data\working\gf10_hpc_tiles64_v2"
if ($LASTEXITCODE -ne 0) { throw 'GF10 tile stage failed' }
Write-Host 'PREFLIGHT_OK. No files downloaded, no GEE task submitted.'
