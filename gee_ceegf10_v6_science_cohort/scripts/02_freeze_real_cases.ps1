param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){$PY=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$env:PYTHONPATH=$P
$src=Join-Path $Root 'outputs\fig1_publication_r3\labels\grid_day_observations.parquet'
$map=Join-Path $P 'config\fig1_verified_column_mapping.json'
$v4=Join-Path $Root 'CEE_GF10_GEE_RECOVERY_V4_20261105\config\recovery.json'
if(-not(Test-Path $map)){throw 'Codex must populate mapping from actual Figure1 source columns/precision QC; no guessed city/date fields'}
if(-not(Test-Path $v4)){throw 'Missing immutable v4 recovery config with GF10 real source'}
$grid=(Get-Content $v4 -Raw | ConvertFrom-Json).grid_path
& $PY -m cee_v6 freeze-cases --source $src --mapping $map --grid $grid --start 2021-01-01 --end 2023-12-31
if($LASTEXITCODE -ne 0){throw 'Figure1 case selection/source precision QC failed'}
