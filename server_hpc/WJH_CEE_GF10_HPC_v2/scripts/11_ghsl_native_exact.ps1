param(
  [switch]$Full,
  [int]$Workers=16
)
$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot
$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1'
$TILES="$ROOT\data\working\gf10_hpc_tiles64_v2"
$names=@('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020')
foreach($p in $names){
  $src="$ROOT\data\staged\${p}_1km\${p}_1km.tif"
  if (!(Test-Path $src)) {Write-Warning "Unstaged native GHSL source: $src";continue}
  & $PY -m gf10hpc verify-source --source $src --profile $p `
    --out "$ROOT\reports\verify_${p}_v2.json"
  if ($LASTEXITCODE -ne 0) {throw "Native GHSL source verification failed $p"}
  $cmd=@('-m','gf10hpc','raster-exact','--tiles',$TILES,'--source',$src,
      '--profile',$p,'--workers',"$Workers",'--out',"$ROOT\data\derived\hpc_exact_${p}_v2")
  if (-not $Full) { $cmd+=@('--max-tiles','12') }
  & $PY @cmd
  if ($LASTEXITCODE -ne 0) {throw "Native source exactextract failed $p"}
}
Write-Host 'Native GHSL extraction done. Check run_qc.json, nonzero valid rows, area totals, and coast flags.'
