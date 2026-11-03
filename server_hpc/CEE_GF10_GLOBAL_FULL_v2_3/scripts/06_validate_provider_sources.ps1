param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $PY)) {throw "Python not found: $PY"}
$env:PYTHONPATH=$PKG
Set-Location $PKG
& $PY -m ceeprod --root $Root verify-providers
if($LASTEXITCODE -ne 0){
    throw "Provider metadata verification failed. Read $Root\reports\cee_full_v2\vector_source_autodetect_v22.json"
}
Write-Host 'ALL SIX VECTOR PROVIDERS FOUND. UCDB themes and real nested HydroATLAS FileGDBs validated.' -ForegroundColor Green
