$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$ZROOT="$ROOT\data\raw\ghsl"
if (!(Test-Path "$TILES\tile_index_qc.json")) { throw 'Run 00_preflight first' }
$jobs=@(
 @{profile='ghsl_built_2000';pattern='GHS_BUILT_S_E2000*1000*.zip';name='ghsl_built_2000_1km'},
 @{profile='ghsl_built_2020';pattern='GHS_BUILT_S_E2020*1000*.zip';name='ghsl_built_2020_1km'},
 @{profile='ghsl_nres_2020';pattern='GHS_BUILT_S_NRES_E2020*1000*.zip';name='ghsl_nres_2020_1km'},
 @{profile='ghsl_pop_2020';pattern='GHS_POP_E2020*1000*.zip';name='ghsl_pop_2020_1km'},
 @{profile='ghsl_smod_2020';pattern='GHS_SMOD_E2020*1000*.zip';name='ghsl_smod_2020_1km'}
)
foreach($job in $jobs) {
 $zips=@(Get-ChildItem $ZROOT -Recurse -File -Filter '*.zip' | Where-Object { $_.Name -like $job.pattern })
 if ($zips.Count -eq 0) { Write-Warning "Not downloaded yet: $($job.profile)"; continue }
 if ($zips.Count -ne 1) { throw "Ambiguous GHSL official ZIP(s) for $($job.profile)" }
 $src="$ROOT\data\staged\$($job.name)\$($job.name).tif"
 & $PY -m gf10hpc stage --zip $zips[0].FullName --member '*.tif' --out $src
 if ($LASTEXITCODE -ne 0) { throw "Stage failed: $($job.profile)" }
 & $PY -m gf10hpc verify-source --source $src --profile $job.profile `
   --out "$ROOT\reports\verify_$($job.profile)_v2.json"
 if ($LASTEXITCODE -ne 0) { throw "Original official GHSL raster source verification failed: $($job.profile)" }
 & $PY -m gf10hpc raster-fast --tiles $TILES --source $src --profile $job.profile `
  --out "$ROOT\data\derived\hpc_$($job.profile)_v2" --workers 16 --gdal-threads 2 --max-tiles 12
 if ($LASTEXITCODE -ne 0) { throw "Raster pilot failed: $($job.profile)" }
}
Write-Host 'GHSL_PILOT_COMPLETE: Read each data/derived/hpc_*/run_qc.json before full run.'
