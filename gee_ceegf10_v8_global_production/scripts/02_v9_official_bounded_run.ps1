param(
    [string]$Root='E:\GEE_flooding',
    [string]$Storage='drive',
    [string]$Bucket='',
    [double]$BudgetLimitEecu=900
)
$ErrorActionPreference='Stop'
$Pkg = Join-Path $Root 'CEE_GF10_GLOBAL_EE_V8_20261106'
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH="$Pkg;$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
Set-Location $Pkg
if (-not (Test-Path "$Pkg\plans\frozen_plan_qc.json")) {
    & $Py -m cee_v8 --root $Root --pkg $Pkg prepare --max-rows 400 --max-days 2
    if ($LASTEXITCODE -ne 0) {throw 'Frozen data/date source failed preflight'}
}
& $Py -m cee_v8.optimizer_cli_v9 --root $Root --pkg $Pkg preview
if ($LASTEXITCODE -ne 0) {throw 'Merit exact land-source conservation failed'}
if (-not (Test-Path "$Pkg\pilot_v9\pilot_plan.csv")) {
    & $Py -m cee_v8.optimizer_cli_v9 --root $Root --pkg $Pkg plan-pilots
    if ($LASTEXITCODE -ne 0) {throw 'Real science canary planning failed'}
}
$arg=@('--root',$Root,'--pkg',$Pkg,'tick-pilots','--storage',$Storage,'--max-inflight','2')
if ($Storage -eq 'gcs') {
    if ([string]::IsNullOrWhiteSpace($Bucket)) {throw 'Authorized bucket required'}
    $arg+=@('--bucket',$Bucket)
}
# Each call is journaled; safe to rerun when Windows session/network disconnects.
& $Py -m cee_v8.optimizer_cli_v9 @arg
if ($LASTEXITCODE -ne 0) {throw 'Pilot task verification failed'}
& $Py -m cee_v8.optimizer_cli_v9 --root $Root --pkg $Pkg status
Write-Host 'Repeat this script until 9 canary tasks terminal. Then run approval/promote/register/run as in README.'
