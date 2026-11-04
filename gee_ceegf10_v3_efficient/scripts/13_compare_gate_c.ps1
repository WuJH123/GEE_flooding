param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PKG
$Out=Join-Path $Root 'data\derived\wc2021_native10m_GF10_v3'
$Ref=Join-Path $Root 'reference\GATE_C_20261104'
& $PY -m ceeprodgee.worldcover_local_compare --tiles $Out --reference $Ref --out (Join-Path $Out 'gate_c_local_vs_gee.json')
if($LASTEXITCODE -ne 0){throw 'Independent Gate C difference too large or baseline reference missing'}
