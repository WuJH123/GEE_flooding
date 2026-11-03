param(
 [string]$Root='E:\WJH_CEE',
 [ValidateRange(1,6)][int]$RasterJobs=4,
 [ValidateRange(1,32)][int]$RasterWorkers=16,
 [ValidateRange(1,3)][int]$VectorJobs=2,
 [ValidateRange(1,32)][int]$VectorWorkers=16
)
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
Set-Location $PKG
& (Join-Path $PSScriptRoot '00_prepare_full.ps1') -Root $Root -SkipPip
if($LASTEXITCODE -ne 0){throw 'Preflight failed: stop full-global task.'}
& (Join-Path $PSScriptRoot '08_prepare_grip_crs.ps1') -Root $Root
if($LASTEXITCODE -ne 0){throw 'GRIP4 WGS84 metadata verification failed: stop full-global task.'}
& (Join-Path $PSScriptRoot '06_validate_provider_sources.ps1') -Root $Root
if($LASTEXITCODE -ne 0){throw 'Official GDB/UCDB source discovery failed: stop full-global task.'}
& (Join-Path $PSScriptRoot '01_run_all_full.ps1') -Root $Root `
 -RasterJobs $RasterJobs -RasterWorkers $RasterWorkers -VectorJobs $VectorJobs -VectorWorkers $VectorWorkers
if($LASTEXITCODE -ne 0){throw 'Production failed; examine reports\cee_full_v2\failed_stage.json; prior successful tiles preserved.'}
Write-Host 'All local global production steps exited successfully; run strict QC next.' -ForegroundColor Green
