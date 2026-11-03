param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY="$Root\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PKG
Set-Location $PKG
& $PY -m ceeprod --root $Root verify --strict
if($LASTEXITCODE -ne 0) {throw 'Not all source families are structurally complete; see reports\cee_global_v2_audit.json'}
Write-Host 'Global structural validation done; publication_ready stays FALSE pending science gates.' -ForegroundColor Green
