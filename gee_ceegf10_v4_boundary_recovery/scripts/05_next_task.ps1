param([switch]$Execute)
. "$PSScriptRoot\00_environment.ps1"
& $PY -m cee_boundary_v4 submit --key auto
if($LASTEXITCODE -ne 0){throw 'No safe next tile available'}
if($Execute){
 $Run=(Get-Content -LiteralPath (Join-Path $V3 'config\production.json') -Raw | ConvertFrom-Json).run_id
 & $PY -m cee_boundary_v4 submit --key auto --execute --confirm "${Run}_BOUNDARY_V4"
 if($LASTEXITCODE -ne 0){throw 'Task not submitted; inspect v4 ledger and QC'}
}
