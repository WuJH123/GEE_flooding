$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
$cfg=Get-Content (Join-Path $ROOT 'config\local_run.json') -Raw | ConvertFrom-Json
Write-Host ('Dedicated GEE project: '+$cfg.project)
Write-Host ('Pilot EECU hours: '+$cfg.pilot_eecu_hours)
$consent=Read-Host ('To approve only ONE 1/12 regional MERIT export, enter run_id '+$cfg.run_id)
if ($consent -ne $cfg.run_id) { throw 'No approval; no global jobs submitted' }
& $PY -m ceegee approve --confirm $consent
if ($LASTEXITCODE -ne 0) { throw 'QA/eecu gate not passed' }
& $PY -m ceegee submit-static --family merit --strip 0 --count 1 --strips 12
if ($LASTEXITCODE -ne 0) { throw 'First regional export not submitted' }
Write-Host 'ONE STRIP SUBMITTED. Download output from isolated Drive folder; validate-tif before remaining regions.'
