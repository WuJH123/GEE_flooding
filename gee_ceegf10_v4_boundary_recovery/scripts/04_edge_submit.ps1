param([switch]$Execute)
. "$PSScriptRoot\00_environment.ps1"
$Key='merit_-1740_-240_10'
& $PY -m cee_boundary_v4 submit --key $Key
if($LASTEXITCODE -ne 0){throw 'Boundary tile dry-run rejected'}
if($Execute){
 $Run=(Get-Content -LiteralPath (Join-Path $V3 'config\production.json') -Raw | ConvertFrom-Json).run_id
 & $PY -m cee_boundary_v4 submit --key $Key --execute --confirm "${Run}_BOUNDARY_V4"
 if($LASTEXITCODE -ne 0){throw 'Boundary task not submitted'}
}
