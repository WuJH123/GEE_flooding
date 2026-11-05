param([string]$Root='E:\GEE_flooding',[string]$Key='merit_-1740_-240_10',[switch]$Execute)
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
$env:PYTHONPATH="$Pkg;$V3"
$Conf=Get-Content (Join-Path $Pkg 'config\recovery.json') -Raw | ConvertFrom-Json
if(-not $Execute){& $PY -m cee_recover.run preview --key $Key}
else{& $PY -m cee_recover.run submit --key $Key --execute --confirm $Conf.run_id}
if($LASTEXITCODE -ne 0){throw 'V4 recovery export rejected; verify safe projected boundary and ledger'}
