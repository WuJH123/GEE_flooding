$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$ZIP="$ROOT\CEE数据\ERA5-EX v4.zip"
$NC="$ROOT\data\staged\era5ex\RX1day_1950_2025.nc"
& $PY -m gf10hpc stage --zip $ZIP --member '*RX1day*1950*2025*.nc' --out $NC
if ($LASTEXITCODE -ne 0) {throw 'Check actual archive member names/case; use Python zipfile.namelist()'}
& $PY -m gf10hpc era5ex --source $NC --grid "$ROOT\gf10_global_nonantarctic_land.parquet" `
 --variable auto --years 2000 2005 2010 2015 2020 2021 2022 2023 2024 2025 `
 --out "$ROOT\data\derived\era5ex_rx1day_annual_v2"
if ($LASTEXITCODE -ne 0) {throw 'Verify real NetCDF coordinate and variable metadata'}
