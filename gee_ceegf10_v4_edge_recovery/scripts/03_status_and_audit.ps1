param([string]$Root='E:\GEE_flooding',[string]$Key='merit_-1740_-240_10',[switch]$Audit)
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
$env:PYTHONPATH="$Pkg;$V3"
& $PY -m cee_recover.run status
if($LASTEXITCODE -ne 0){throw 'GEE operation status fetch failed'}
if($Audit){& $PY -m cee_recover.run audit --key $Key}
if($LASTEXITCODE -ne 0){throw 'Local downloaded GeoTIFF failed immutable GF10 shape/affine/science QC'}
