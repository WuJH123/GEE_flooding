param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PACKAGE=Split-Path -Parent $PSScriptRoot
$PY="$Root\.venv\Scripts\python.exe"
if(-not(Test-Path $PY)){throw 'Missing existing Python venv'}
$env:PYTHONPATH=$PACKAGE
Set-Location $PACKAGE
$reportDir="$Root\reports\cee_full_v2"
New-Item -ItemType Directory -Force $reportDir | Out-Null
$log="$reportDir\gisd_rar_staging_v21_$(Get-Date -Format yyyyMMdd_HHmmss).log"
$prior=$ErrorActionPreference
try{
 $ErrorActionPreference='Continue'
 & $PY -u (Join-Path $PSScriptRoot 'run_with_log.py') --log $log --cwd $PACKAGE -- $PY -u -m ceeprod --root $Root stage --family gisd
 $exitCode=$LASTEXITCODE
}finally{$ErrorActionPreference=$prior}
if($exitCode -ne 0){
 Get-Content $log -Tail 80
 throw "GISD30 source staging FAILED: see full original Python stack trace in $log"
}
Write-Host 'GISD30 12-RAR stage done or safely resumed; no 1.4M GF10 metrics computed yet.' -ForegroundColor Green
