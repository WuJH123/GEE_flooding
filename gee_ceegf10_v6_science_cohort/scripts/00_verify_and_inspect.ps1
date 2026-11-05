param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)){$PY=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
if(-not(Test-Path $PY)){throw 'Cannot find existing Python venv; install requirements using your existing project environment'}
$V3=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'
if(-not(Test-Path $V3)){$V3=Join-Path $Root 'gee_ceegf10_v3_efficient'}
if(-not(Test-Path (Join-Path $V3 'ceeprodgee\ee_model.py'))){throw 'Verified source MERIT 16-band model v3 not found'}
$env:PYTHONPATH="$P;$V3"
Push-Location $P
try {
 & $PY -m compileall -q cee_v6
 if($LASTEXITCODE -ne 0){throw 'V6 source compile error'}
 & $PY -m pytest -q -W error tests
 if($LASTEXITCODE -ne 0){throw 'V6 regressions failed; no GEE permitted'}
 $V5=Join-Path $Root 'CEE_GF10_GEE_PRODUCTION_V5\reports\v5_science_equivalence.json'
 if(Test-Path $V5){Get-Content $V5 -Raw}
 Write-Host 'V6_OFFLINE_TESTS_OK; V5 scientific FAIL remains blocking until live 40/80km convergence passes'
}finally{Pop-Location}
