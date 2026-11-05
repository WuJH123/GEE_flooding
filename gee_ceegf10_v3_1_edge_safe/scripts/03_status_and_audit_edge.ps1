param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$P
& $py -m ceeprodgee status
if ($LASTEXITCODE -ne 0) {throw 'Status fetch failed'}
$ledger=Get-Content (Join-Path $P 'reports\task_ledger.json') -Raw | ConvertFrom-Json
$rec=$ledger | Where-Object { $_.key -match '^merit_-1740_-240_10_edgefix\d+$' } | Select-Object -Last 1
if (!$rec) {throw 'Repair entry not found in task registry'}
$file=Join-Path $P ('downloads\'+$rec.file)
if (!(Test-Path $file)) {
 Write-Warning ('Copy the completed CSV from Google Drive to '+$file)
 Write-Host ('Expected filename: '+$rec.file)
 exit 2
}
& $py -m ceeprodgee audit --key $rec.key --file $file
if ($LASTEXITCODE -ne 0) {throw 'Local CSV row/ID/physics QA failed'}
Write-Host 'EDGE_CSV_QC_PASS. Check original audit and run representative second boundary pilot.'
