param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104';$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
$events=Join-Path $P 'config\gf10_event_dates.parquet'
if (-not (Test-Path $events)){
 throw 'Copy the scientifically frozen GF10 (NOT 20km) grid_id,date_utc event+control table to config\gf10_event_dates.parquet. Cannot invent flood controls.'
}
& $PY -m ceeopt weather-plan --events $events --block 50
if ($LASTEXITCODE -ne 0){throw 'UTC GF10 date cohort failed input science QA'}
