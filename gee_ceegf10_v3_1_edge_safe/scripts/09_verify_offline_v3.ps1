$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$Candidates=@('E:\GEE_flooding\.venv\Scripts\python.exe','E:\WJH_CEE\.venv\Scripts\python.exe', (Join-Path $PKG '.venv\Scripts\python.exe'))
$PY=$Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if(-not $PY){ throw 'No project Python virtual environment available' }
$env:PYTHONPATH=$PKG
Push-Location $PKG
try{
 & $PY -m compileall -q ceeprodgee
 if($LASTEXITCODE -ne 0){throw 'Cannot compile production source'}
 & $PY -m pytest tests -q
 if($LASTEXITCODE -ne 0){throw 'Regression tests failed'}
 Write-Host 'OFFLINE_V3_TESTS_PASS; no GEE tasks submitted'
}finally{Pop-Location}
