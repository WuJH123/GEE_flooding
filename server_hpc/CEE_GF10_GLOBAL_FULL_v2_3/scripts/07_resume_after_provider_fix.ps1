param(
    [string]$Root='E:\WJH_CEE',
    [ValidateRange(1,6)][int]$RasterJobs=4,
    [ValidateRange(1,32)][int]$RasterWorkers=16,
    [ValidateRange(1,3)][int]$VectorJobs=2,
    [ValidateRange(1,32)][int]$VectorWorkers=16
)
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
if(-not(Test-Path "$Root\gf10_global_nonantarctic_land.parquet")){
    throw 'Frozen GF10 base not found; check Root parameter'
}
Set-Location $PKG
Write-Host '[1/3] Validate unchanged frozen grid, local inputs, Python and new tests...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot '00_prepare_full.ps1') -Root $Root -SkipPip
if($LASTEXITCODE -ne 0){throw 'Package verification failed; global jobs not started'}
Write-Host '[2/3] Audit real nested HydroATLAS FileGDBs and all UCDB themes...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot '06_validate_provider_sources.ps1') -Root $Root
if($LASTEXITCODE -ne 0){throw 'Provider validation failed; global jobs not started'}
Write-Host '[3/3] Resume all 715-tile global local data production...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot '01_run_all_full.ps1') -Root $Root `
 -RasterJobs $RasterJobs -RasterWorkers $RasterWorkers `
 -VectorJobs $VectorJobs -VectorWorkers $VectorWorkers
if($LASTEXITCODE -ne 0){throw 'Global production failed; inspect reports/cee_full_v2/failed_stage.json'}
Write-Host 'GLOBAL FULL PROCESSING FINISHED: run strict validation next.' -ForegroundColor Green
