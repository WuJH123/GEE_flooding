param([string]$Root='E:\WJH_CEE', [string]$Package=$PSScriptRoot)
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){throw 'Server venv not found: E:\WJH_CEE\.venv\Scripts\python.exe'}
$env:PYTHONPATH=$PKG
$Grid=Join-Path $Root 'gf10_global_nonantarctic_land.parquet'
$Raw=Join-Path $Root 'data\raw\ESA_WorldCover_2021_v200_COG'
$Plan=Join-Path $PKG 'plans\worldcover_local_pilot_four.csv'
$Out=Join-Path $Root 'data\derived\wc2021_native10m_GF10_v3'
& $PY -m ceeprodgee.worldcover_local_plan --grid $Grid --scope pilot-four --out $Plan
if($LASTEXITCODE -ne 0){throw 'Cannot make frozen pilot plan'}
& $PY -m ceeprodgee.worldcover_local --source $Raw --grid $Grid --gshhg $Root --plan $Plan --out $Out --workers 8
if($LASTEXITCODE -ne 0){throw 'Local WorldCover four-area 10m extraction failed'}
