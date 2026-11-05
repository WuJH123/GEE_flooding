param([string]$Root='E:\GEE_flooding',[int]$Candidates=8)
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){$PY=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$env:PYTHONPATH=$P
$v4=Join-Path $Root 'CEE_GF10_GEE_RECOVERY_V4_20261105\config\recovery.json'
$grid=(Get-Content $v4 -Raw | ConvertFrom-Json).grid_path
$C=Join-Path $P 'data\cohort_v6'
& $PY -m cee_v6 calendar-candidates --cases (Join-Path $C 'reported_grid_day_cases.parquet') --per-case $Candidates
if($LASTEXITCODE -ne 0){throw 'Calendar control candidate selection failed'}
& $PY -m cee_v6 weather-request-plan --cohort (Join-Path $C 'preweather_reported_and_unlabeled_candidates.parquet') --grid $grid
if($LASTEXITCODE -ne 0){throw 'GF10 x UTC-day event plan failed'}
Write-Host 'PRE_WEATHER_PLAN_BUILT; no actual no-flood labels or storm IDs have been inferred'
