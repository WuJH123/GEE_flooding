param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PKG
$Grid=Join-Path $Root 'gf10_global_nonantarctic_land.parquet'
$Plan=Join-Path $PKG 'plans\worldcover_local_all.csv'
$Dir=Join-Path $Root 'data\derived\wc2021_native10m_GF10_v3'
$Output=Join-Path $Root 'data\derived\wc2021_native10m_GF10_v3\gf10_worldcover2021_all_land.parquet'
& $PY -m ceeprodgee.worldcover_local_merge --grid $Grid --plan $Plan --tiles $Dir --out $Output
if($LASTEXITCODE -ne 0){throw 'Global official WorldCover COG tile join QC failed'}
