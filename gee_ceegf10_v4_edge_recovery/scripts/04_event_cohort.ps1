param([string]$Root='E:\GEE_flooding',[string]$Cohort='')
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
$env:PYTHONPATH="$Pkg;$V3"
if(-not $Cohort){
 Write-Host 'STOP: audited case/control GF10 x UTC-day cohort is not yet available. Figure 1 observations are not controls.'
 Write-Host 'Required columns: grid_id date_utc case_control pair_id storm_id city_id label_source sampling_protocol'
 return
}
& $PY -m cee_recover.events --input $Cohort
if($LASTEXITCODE -ne 0){throw 'Case/control cohort audit failed; no GEE submissions allowed'}
