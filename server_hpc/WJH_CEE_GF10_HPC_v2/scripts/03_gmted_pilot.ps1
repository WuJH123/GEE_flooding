$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$files=@(
 @{name='gmted_elevation';file='elevation_1KMmn_GMTEDmn.tif'},
 @{name='gmted_slope';file='slope_1KMmn_GMTEDmd.tif'},
 @{name='gmted_roughness';file='roughness_1KMmn_GMTEDmd.tif'},
 @{name='gmted_tpi';file='tpi_1KMmn_GMTEDmd.tif'},
 @{name='gmted_tri';file='tri_1KMmn_GMTEDmd.tif'}
)
foreach($j in $files){
 $source="$ROOT\CEE数据\$($j.file)"
 if (!(Test-Path $source)) { Write-Warning "Missing TIFF: $source"; continue }
 & $PY -m gf10hpc raster-fast --tiles $TILES --source $source --profile $j.name `
  --out "$ROOT\data\derived\hpc_$($j.name)_v2" --workers 16 --gdal-threads 2 --max-tiles 12
 if ($LASTEXITCODE -ne 0) {throw "GMTED pilot failed $($j.name)"}
}
Write-Warning 'GMTED elevation mean/max metadata contradiction and slope unit need verification before final publication.'
