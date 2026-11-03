$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$jobs=@('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020')
foreach($j in $jobs) {
 $source="$ROOT\data\staged\${j}_1km\${j}_1km.tif"
 if (!(Test-Path $source)) { Write-Warning "No staged source $source"; continue }
 $OUT="$ROOT\data\derived\hpc_${j}_v2"
 & $PY -m gf10hpc raster-fast --tiles $TILES --source $source --profile $j `
  --out $OUT --workers 24 --gdal-threads 2
 if ($LASTEXITCODE -ne 0) { throw "FAILED: $j; inspect tile QC; retry same command only after diagnosis" }
}
Write-Host 'FULL_GHSL_DONE_NEEDS_INDEPENDENT_EXACT_PIXEL_AND_COAST_QA'
