param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){$PY=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$V3=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'
if(-not(Test-Path $V3)){$V3=Join-Path $Root 'gee_ceegf10_v3_efficient'}
$env:PYTHONPATH="$P;$V3"
foreach($key in @('merit_1090_360_10','merit_700_230_10','merit_-1720_670_10')){
 foreach($halo in @(20,40,80)){
  & $PY -m cee_v6 halo-submit --root $Root --key $key --halo $halo
  if($LASTEXITCODE -ne 0){throw "Halo dry-run failed $key $halo"}
 }
}
$plan=Join-Path $P 'plans\event_requests_v6.csv'
if(Test-Path $plan){
 $first=Import-Csv $plan | Select-Object -First 1
 if($null -ne $first){& $PY -m cee_v6 weather-submit --root $Root --key $first.request_key}
}else{Write-Host 'Event plan not ready; first construct audited source report cases and calendar candidates'}
