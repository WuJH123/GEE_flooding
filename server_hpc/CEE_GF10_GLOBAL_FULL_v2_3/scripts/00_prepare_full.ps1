param(
 [string]$Root='E:\WJH_CEE',
 [switch]$SkipPip
)
$ErrorActionPreference='Stop'
$PACKAGE=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $PY)) {throw "Existing Python environment is missing: $PY"}
if (-not (Test-Path "$Root\gf10_global_nonantarctic_land.parquet")) {throw 'Frozen GF10 original base is missing'}
$env:PYTHONPATH=$PACKAGE
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:GDAL_NUM_THREADS='1'
Set-Location $PACKAGE
& $PY (Join-Path $PACKAGE 'scripts\verify_package.py') --root $PACKAGE
if($LASTEXITCODE -ne 0) {throw 'Offline ZIP source integrity verification failed'}
if (-not $SkipPip) {
 & $PY -m pip install --disable-pip-version-check --only-binary=:all: -r "$PACKAGE\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
 if($LASTEXITCODE -ne 0) {throw 'Dependency installation failed'}
}
& $PY -c "import pandas,pyarrow,rasterio,exactextract,geopandas,pyogrio,xarray,netCDF4,psutil,scipy; print('CORE_DEPENDENCIES_OK')"
if($LASTEXITCODE -ne 0) {throw 'Required Python import failed'}
& $PY -m pytest -q tests
if($LASTEXITCODE -ne 0) {throw 'Tests failed; production refused'}
& $PY -m ceeall --root $Root inventory
if($LASTEXITCODE -ne 0) {throw 'Local 35-file inventory failed'}
& $PY -m ceeall --root $Root grid-tiles
if($LASTEXITCODE -ne 0) {throw 'Frozen global GF10 tile index failed'}
& $PY -m ceeprod --root $Root plan
if($LASTEXITCODE -ne 0) {throw 'All-local source plan failed'}
Write-Host 'PREPARE_COMPLETE: no cloud/GitHub; original files preserved; full-production can be started.' -ForegroundColor Green
