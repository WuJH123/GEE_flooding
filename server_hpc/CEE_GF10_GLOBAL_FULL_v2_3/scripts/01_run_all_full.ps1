param(
 [string]$Root='E:\WJH_CEE',
 [ValidateRange(1,6)][int]$RasterJobs=4,
 [ValidateRange(1,32)][int]$RasterWorkers=16,
 [ValidateRange(1,3)][int]$VectorJobs=2,
 [ValidateRange(1,32)][int]$VectorWorkers=16,
 [switch]$StageOnly
)
$ErrorActionPreference='Stop'
if($RasterJobs*$RasterWorkers -gt 96) {throw 'Total raster process count >96 not allowed'}
if($VectorJobs*$VectorWorkers -gt 64) {throw 'Total vector process count >64 not allowed'}
$PACKAGE=Split-Path -Parent $PSScriptRoot
$PY="$Root\.venv\Scripts\python.exe"
if(-not(Test-Path $PY)) {throw "No Python: $PY"}
$env:PYTHONPATH=$PACKAGE
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1';$env:MKL_NUM_THREADS='1';$env:GDAL_NUM_THREADS='1'
Set-Location $PACKAGE
$reportDir="$Root\reports\cee_full_v2"
New-Item -ItemType Directory -Force $reportDir | Out-Null
$log="$reportDir\full_run_v22_$(Get-Date -Format yyyyMMdd_HHmmss).log"
Write-Host "GF10 ALL LOCAL DATA PRODUCTION: 1,395,471 GF10 / 715 tiles. Raster workers=$RasterJobs x $RasterWorkers" -ForegroundColor Cyan
Write-Host "Full stdout + traceback in: $log"
$argsList=@('-u','-m','ceeprod','--root',$Root,'run',
 '--raster-jobs',"$RasterJobs",'--raster-workers',"$RasterWorkers",
 '--vector-jobs',"$VectorJobs",'--vector-workers',"$VectorWorkers")
if($StageOnly) {$argsList+=@('--stage-only')}
# Python streams child stdout and stderr to one stdout stream; PowerShell 5.1
# cannot prematurely interpret the child's first traceback line as a native error.
# Child's nonzero exit code is preserved and shown with a useful log tail.
$previousPreference=$ErrorActionPreference
try {
 $ErrorActionPreference='Continue'
 & $PY -u (Join-Path $PSScriptRoot 'run_with_log.py') --log $log --cwd $PACKAGE -- $PY @argsList
 $exitCode=$LASTEXITCODE
}
finally {$ErrorActionPreference=$previousPreference}
if($exitCode -ne 0) {
 Write-Host "FULL RUN FAILED exit=$exitCode; full traceback: $log" -ForegroundColor Red
 if(Test-Path $log) {Get-Content $log -Tail 75}
 $failure="$reportDir\failed_stage.json"
 if(Test-Path $failure) {Write-Host "Structured error: $failure" -ForegroundColor Yellow;Get-Content $failure -Raw}
 throw "GLOBAL RUN FAILED exit=$exitCode. Completed outputs preserved. Follow instructions in $failure."
}
if($StageOnly) {Write-Host 'ALL SOURCE ARCHIVES STAGED. No global metric computation executed.' -ForegroundColor Green}
else {Write-Host 'ALL LOCAL TASKS STRUCTURALLY COMPLETE; publication-level source and land QA still necessary.' -ForegroundColor Green}
