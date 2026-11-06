param([string]$Root='E:\GEE_flooding',[string]$Pkg='')
$ErrorActionPreference='Stop'
if(-not $Pkg){$Pkg=Join-Path $Root 'CEE_GF10_GLOBAL_EE_V8_20261106'}
$Py=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $Py)){throw "Missing python venv: $Py"}
$env:PYTHONPATH="$Pkg;$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
& $Py -m pip install -r (Join-Path $Pkg 'requirements.txt')
if($LASTEXITCODE -ne 0){throw 'Install dependencies failed'}
& $Py -m pytest (Join-Path $Pkg 'tests') -q -W error
if($LASTEXITCODE -ne 0){throw 'Do not start global production: tests failed'}
& $Py -m cee_v8 --root $Root --pkg $Pkg prepare
if($LASTEXITCODE -ne 0){throw 'Scientific source freezing/plan failed'}
& $Py -m cee_v8 --root $Root --pkg $Pkg register
if($LASTEXITCODE -ne 0){throw 'Durable ledger initialization failed'}
& $Py -m cee_v8 --root $Root --pkg $Pkg status
