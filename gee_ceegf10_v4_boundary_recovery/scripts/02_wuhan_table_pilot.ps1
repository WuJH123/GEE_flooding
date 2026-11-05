param([switch]$Execute)
. "$PSScriptRoot\00_environment.ps1"
$Key='merit_1097_367_10_TABLE_PILOT'
& $PY -m cee_boundary_v4 submit --key $Key
if($LASTEXITCODE -ne 0){throw 'Table pilot dry-run failed'}
if($Execute){
 $Run=(Get-Content -LiteralPath (Join-Path $V3 'config\production.json') -Raw | ConvertFrom-Json).run_id
 & $PY -m cee_boundary_v4 submit --key $Key --execute --confirm "${Run}_BOUNDARY_V4"
 if($LASTEXITCODE -ne 0){throw 'Table pilot submission failed; do not start next step'}
}
