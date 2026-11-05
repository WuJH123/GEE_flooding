param([string]$Root='E:\GEE_flooding', [string]$BadTif='')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $py)) {throw 'Original Python virtual environment missing'}
$env:PYTHONPATH=$P
$conf=(Get-Content (Join-Path $P 'config\production.json') -Raw | ConvertFrom-Json)
$plan=Join-Path $P 'plans\merit_all.csv'
if (!(Test-Path $plan)) {
  & $py -m ceeprodgee plan --family merit --scope all
  if ($LASTEXITCODE -ne 0) {throw 'Planning failed'}
}
$argv=@('-m','ceeprodgee','submit','--family','merit','--plan',$plan,
        '--tile-key','merit_-1740_-240_10','--execute','--confirm',$conf.run_id,
        '--repair-ack','REJECT_3474X10_EXPORT')
if ($BadTif) {$argv+=@('--bad-tif',$BadTif)}
Write-Host 'SUBMIT ONE edge CSV repair ONLY. This consumes EECU but preserves the failed task.'
& $py @argv
if ($LASTEXITCODE -ne 0) {throw 'Edge repair submission failed; read the full traceback, do not submit another task'}
