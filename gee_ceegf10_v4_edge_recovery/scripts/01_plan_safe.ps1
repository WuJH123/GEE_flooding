param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
if(-not $PY){throw 'No valid Python virtual environment'}
$env:PYTHONPATH="$Pkg;$V3"
& $PY -m cee_recover.run plan
if($LASTEXITCODE -ne 0){throw 'Safe tile plan not frozen'}
& $PY -m cee_recover.run preview --key merit_-1740_-240_10
if($LASTEXITCODE -ne 0){throw 'First west-edge crop not safe; quarantine rather than exporting'}
