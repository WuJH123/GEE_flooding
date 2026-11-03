# Compare I/O throughput vs CPU saturation on a fixed 24-tile GHSL sample.
$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot
$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1';$env:MKL_NUM_THREADS='1'
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$SRC="$ROOT\data\staged\ghsl_built_2020_1km\ghsl_built_2020_1km.tif"
if (!(Test-Path $SRC)) { throw 'Run 01_ghsl_pilot to unpack verified original data first' }
foreach($w in @(8,16,24,32,48)) {
    $o="$ROOT\data\derived\benchmark_ghsl2020_w${w}_v3"
    & $PY -m gf10hpc raster-fast --tiles $TILES --source $SRC `
      --profile ghsl_built_2020 --workers $w --gdal-threads 2 `
      --max-tiles 24 --out $o
    if ($LASTEXITCODE -ne 0) { throw "Benchmark failed workers=$w" }
    $j=Get-Content "$o\run_qc.json" -Raw | ConvertFrom-Json
    Write-Host "workers=$w elapsed=$($j.elapsed_s) throughput_tiles_per_s=$($j.tiles_per_second)"
}
Write-Warning 'Compare actual SSD/disk throughput, memory, and tiles/second; 96 runnable threads do not imply 96 productive workers.'
