param([string]$Root='E:\GEE_flooding',[switch]$Execute)
$ErrorActionPreference='Stop';$P=Split-Path $PSScriptRoot -Parent
$Py=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $Py)) {$Py=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$env:PYTHONPATH="$P;$(Join-Path $Root 'CEE_GF10_V6_SCIENCE_COHORT_20261105');$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
$plan=Join-Path $Root 'CEE_GF10_FIG1_AUDIT_GEE_V7_20261106\plans\gee_weather_date_tile_plan.csv'
if(-not(Test-Path $plan)){throw "Missing audited plan $plan"}
$r=Import-Csv $plan | Where-Object {[int]$_.n_grid_days -le 40} | Select-Object -First 1
if($null -eq $r){throw 'No bounded real weather group'}
& $Py -m cee_v7 --root $Root weather-submit --key $r.request_key
if($LASTEXITCODE -ne 0){throw 'Dry-run failed'}
if($Execute){
 & $Py -m cee_v7 --root $Root weather-submit --key $r.request_key --execute --confirm CEE_GF10_FIG1_AUDIT_GEE_V7_20261106
 if($LASTEXITCODE -ne 0){throw 'Live job rejected; inspect ledger before retry'}
}
