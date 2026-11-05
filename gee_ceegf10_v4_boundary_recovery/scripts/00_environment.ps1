$ErrorActionPreference='Stop'
$ROOT='E:\GEE_flooding'
$PKG=Split-Path -Parent $PSScriptRoot
$V3Candidates=@(
 (Join-Path $ROOT 'CEE_GF10_EFFICIENT_V3_20261105'),
 (Join-Path $ROOT 'gee_ceegf10_v3_efficient')
)
$V3=$V3Candidates | Where-Object {Test-Path (Join-Path $_ 'ceeprodgee\cli.py')} | Select-Object -First 1
if(-not $V3){throw 'V3 package missing; deploy source from GitHub main, do not create empty config'}
$PythonCandidates=@((Join-Path $V3 '.venv\Scripts\python.exe'),(Join-Path $ROOT '.venv\Scripts\python.exe'))
$PY=$PythonCandidates | Where-Object {Test-Path $_} | Select-Object -First 1
if(-not $PY){throw 'Existing v3 virtual environment missing'}
$env:PYTHONPATH="$PKG;$V3"
Write-Host "CEE V4 root $PKG / preexisting V3 $V3 / Python $PY"
