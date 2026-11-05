param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){$PY=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$env:PYTHONPATH=$P
$Source=Join-Path $Root 'outputs\fig1_publication_r3\labels\grid_day_observations.parquet'
if(-not(Test-Path $Source)){throw "Figure1 high-specificity source missing: $Source; Codex must audit actual local Figure1 files, not invent labels"}
& $PY -m cee_v6 inspect-fig1 --source $Source --report (Join-Path $P 'reports\fig1_actual_schema.json')
if($LASTEXITCODE -ne 0){throw 'Figure1 source schema audit failed'}
