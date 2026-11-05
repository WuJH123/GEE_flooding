$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $PKG '.venv\Scripts\python.exe'
# Read the exact immutable ID from this V3 code package's configuration.
$Conf=Join-Path $PKG 'config\production.json'
if(-not(Test-Path $Conf)){throw 'Run scripts\00_preflight.ps1 to configure the isolated CEE GEE project first'}
$RunId=(Get-Content -LiteralPath $Conf -Raw | ConvertFrom-Json).run_id
if(-not $RunId){throw 'Missing v3 run_id in configuration'}
Push-Location $PKG
try { & $PY -m ceeprodgee verify --strict-coast
 if ($LASTEXITCODE -ne 0) {throw 'Cannot use GSHHG land geometry'}
 & $PY -m ceeprodgee submit --family worldcover --pilot --execute --confirm $RunId
 if ($LASTEXITCODE -ne 0) {throw 'WorldCover pilot submission failed'}
} finally {Pop-Location}
