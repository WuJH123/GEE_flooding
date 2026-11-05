param([string]$Root='E:\WJH_CEE',[int]$Workers=8)
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PKG
$Grid=Join-Path $Root 'gf10_global_nonantarctic_land.parquet'
$Raw=Join-Path $Root 'data\raw\ESA_WorldCover_2021_v200_COG'
$Plan=Join-Path $PKG 'plans\worldcover_local_all.csv'
$Out=Join-Path $Root 'data\derived\wc2021_native10m_GF10_v3'
$Gate=Join-Path $Out 'gate_c_local_vs_gee.json'
if(-not(Test-Path $Gate)){throw 'Gate C independent comparison not run: execute scripts\13_compare_gate_c.ps1 first'}
$r=Get-Content $Gate -Raw | ConvertFrom-Json
if($r.status -ne 'PASS_GATE_C_INDEPENDENT_COMPARISON'){throw 'Gate C equality check FAIL; do not claim full global results'}
& $PY -m ceeprodgee.worldcover_local_plan --grid $Grid --scope all --out $Plan
if($LASTEXITCODE -ne 0){throw 'WorldCover global plan failed'}
& $PY -m ceeprodgee.worldcover_local --source $Raw --grid $Grid --gshhg $Root --plan $Plan --out $Out --workers $Workers
if($LASTEXITCODE -ne 0){throw 'WorldCover global extraction incomplete; restart same command after resolving source issue'}
