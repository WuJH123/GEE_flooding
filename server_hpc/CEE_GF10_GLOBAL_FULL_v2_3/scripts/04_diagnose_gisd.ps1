param([string]$Root='E:\WJH_CEE',[switch]$TestAllRar)
$ErrorActionPreference='Stop'
$PACKAGE=Split-Path -Parent $PSScriptRoot
$PY="$Root\.venv\Scripts\python.exe"
$env:PYTHONPATH=$PACKAGE
Set-Location $PACKAGE
$cmd=@('-u','-m','ceeprod','--root',$Root,'doctor')
if ($TestAllRar){$cmd+='--test-rar'}
& $PY @cmd
if ($LASTEXITCODE -ne 0) { throw 'Doctor reports preflight failure. See E:\WJH_CEE\reports\cee_full_v2\diagnostic_v21.json' }
Write-Host 'Diagnostic saved under reports\cee_full_v2\diagnostic_v21.json' -ForegroundColor Green
