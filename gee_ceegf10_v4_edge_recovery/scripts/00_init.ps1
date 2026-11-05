param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$Pkg=Split-Path -Parent $PSScriptRoot
$V3=@((Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'),(Join-Path $Root 'gee_ceegf10_v3_efficient')) | Where-Object { Test-Path (Join-Path $_ 'config\production.json') } | Select-Object -First 1
if(-not $V3){throw 'No verified v3 production.json; use the local code dir reported by Codex'}
$PY=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $Root '.venv\Scripts\python.exe')) | Where-Object { Test-Path $_ } | Select-Object -First 1
if(-not $PY){throw 'No Python venv; install v3 requirements and Earth Engine API first'}
$env:PYTHONPATH="$Pkg;$V3"
Push-Location $Pkg
try {
 & $PY -m pytest tests -q -W error
 if($LASTEXITCODE -ne 0){throw 'V4 recovery regression tests fail; NO GEE SUBMISSION'}
 & $PY -m cee_recover.run init --v3 $V3 --max-eecu 300
 if($LASTEXITCODE -ne 0){throw 'V3 provenance and freeze failed'}
 Write-Host 'V4_INITIALIZED; project and v3 ledger kept unchanged; no GEE jobs submitted'
} finally {Pop-Location}
