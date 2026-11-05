param([switch]$Execute)
. "$PSScriptRoot\00_environment.ps1"
$Key='merit_1097_367_10_TABLE_PILOT'
$Settings=Join-Path $PKG 'reports\boundary_v4_settings.json'
if(-not(Test-Path $Settings)){throw 'Run scripts\03_quarantine_v3_edge.ps1 first; v3 rejected 3474x10 task must be reconciled before online pilot'}
& $PY -m cee_boundary_v4 submit --key $Key
if($LASTEXITCODE -ne 0){throw 'Table pilot dry-run failed'}
if($Execute){
 $Run=(Get-Content -LiteralPath (Join-Path $V3 'config\production.json') -Raw | ConvertFrom-Json).run_id
 & $PY -m cee_boundary_v4 submit --key $Key --execute --confirm "${Run}_BOUNDARY_V4"
 if($LASTEXITCODE -ne 0){throw 'Table pilot submission failed; do not start next step'}
}
