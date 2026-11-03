$ErrorActionPreference = 'Stop'
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT
$venv = Join-Path $ROOT '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { py -3.12 -m venv $venv 2>$null }
if (-not (Test-Path $py)) { py -m venv $venv }
if (-not (Test-Path $py)) { throw 'Python 3 virtual environment creation failed' }
& $py -m pip install -r (Join-Path $ROOT 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies installation failed' }
$env:PYTHONPATH = $ROOT
& $py -m pytest -q tests
if ($LASTEXITCODE -ne 0) { throw 'Tests failed - no GEE tasks will be started' }
$choices = @(
    (Join-Path $ROOT 'gf10_global_nonantarctic_land.parquet'),
    'E:\WJH_CEE\gf10_global_nonantarctic_land.parquet',
    'E:\GEE_flooding\data\reference\gf10_global_nonantarctic_land.parquet'
)
$grid = $choices | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $grid) { throw 'Copy gf10_global_nonantarctic_land.parquet (about 10MB) beside this script; rerun setup' }
if (Test-Path (Join-Path $ROOT 'config\local_run.json')) {
    Write-Host 'CEE GEE config already exists; retaining project isolation.'
} else {
    $project = Read-Host 'Enter NEW dedicated Google Cloud Earth Engine project ID (one time)'
    & $py -m ceegee setup --project $project --grid $grid
    if ($LASTEXITCODE -ne 0) { throw 'Local GEE configuration invalid' }
}
& $py -c 'import ee; ee.Authenticate(auth_mode="localhost")'
if ($LASTEXITCODE -ne 0) { throw 'Google Earth Engine authentication failed' }
Write-Host 'SETUP_OK_LOCAL; no exports submitted yet.'
