$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$items=@('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020')
$cmd=@('-m','gf10hpc','--root',$ROOT,'assemble',
 '--out',"$ROOT\data\derived\gf10_global_static_v2.parquet")
foreach($item in $items) {
 $dir="$ROOT\data\derived\hpc_exact_${item}_v2"
 if (!(Test-Path "$dir\run_qc.json")) {
   $dir="$ROOT\data\derived\hpc_${item}_v2"
 }
 if (!(Test-Path "$dir\run_qc.json")) { throw "Product incomplete: $dir" }
 $qc=Get-Content "$dir\run_qc.json" -Raw | ConvertFrom-Json
 if ($qc.status -notin @('ALL_TILES_FAST_APPROX_NEEDS_EXACT_AND_COAST_QA',
                         'ALL_TILES_NATIVE_EXACT_NEEDS_COAST_QA')) {
  throw "Product not full, or only pilot: $item"
 }
 if ($qc.status -eq 'ALL_TILES_FAST_APPROX_NEEDS_EXACT_AND_COAST_QA') {
    Write-Warning "Including approximate raster-fast product for $item. Not publication-ready."
 }
 $cmd+=@('--product',$dir)
}
& $PY @cmd
if ($LASTEXITCODE -ne 0) {throw 'Static table failed physical invariants / source completeness'}
Write-Host 'Static wide table created; publication_ready=false until exact-area, source units and coastal-mask QA.'
