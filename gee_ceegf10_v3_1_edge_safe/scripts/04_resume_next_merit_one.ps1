param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe';$env:PYTHONPATH=$P
$conf=Get-Content (Join-Path $P 'config\production.json') -Raw | ConvertFrom-Json
$plan=Join-Path $P 'plans\merit_all.csv'
if (!(Test-Path $plan)) {
  & $py -m ceeprodgee plan --family merit --scope all
  if ($LASTEXITCODE -ne 0) {throw 'Frozen plan generation failed'}
}
# This is deliberately one manual task, not a 16,874-task automatic launch.
& $py -m ceeprodgee submit --family merit --plan $plan --tile-key auto --execute --confirm $conf.run_id
if ($LASTEXITCODE -ne 0) {throw 'Next MERIT submission was blocked by a quality or cost gate'}
Write-Host 'ONE_MERIT_TILE_SUBMITTED: wait for completion, download output and run audit before next.'
