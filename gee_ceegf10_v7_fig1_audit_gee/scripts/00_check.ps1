param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop';$P=Split-Path $PSScriptRoot -Parent
$Py=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $Py)) { $Py=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe' }
if(-not(Test-Path $Py)){throw "Python venv not found in $Root"}
$env:PYTHONPATH="$P;$(Join-Path $Root 'CEE_GF10_V6_SCIENCE_COHORT_20261105');$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
& $Py -m pytest "$P\tests" -q -W error
if($LASTEXITCODE -ne 0){throw 'V7 tests fail; no cloud tasks allowed'}
& $Py -m cee_v7 --root $Root inspect
if($LASTEXITCODE -ne 0){throw 'Source inventory failed'}
