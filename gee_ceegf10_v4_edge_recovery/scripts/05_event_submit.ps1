param([string]$Root='E:\GEE_flooding',[string]$Key,[switch]$Execute)
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
$env:PYTHONPATH="$Pkg;$V3"
if(-not $Key){throw 'Specify a real frozen event tile key from event_gee_tasks_v4.csv; no fabricated dates'}
$Conf=Get-Content (Join-Path $Pkg 'config\recovery.json') -Raw | ConvertFrom-Json
if(-not $Execute){& $PY -m cee_recover.event_gee --key $Key}
else{& $PY -m cee_recover.event_gee --key $Key --execute --confirm $Conf.run_id}
if($LASTEXITCODE -ne 0){throw 'Event extraction failed; no repeat tasks without QC'}
