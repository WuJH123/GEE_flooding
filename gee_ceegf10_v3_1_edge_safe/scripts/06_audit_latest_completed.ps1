param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$P
$ledgerPath=Join-Path $P 'reports\task_ledger.json'
if (!(Test-Path $ledgerPath)) {throw 'Import state first'}
$registry=@(Get-Content $ledgerPath -Raw | ConvertFrom-Json)
$target=$registry | Where-Object {
    $_.family -eq 'merit' -and $_.local_qc_pass -eq $false -and !$_.superseded_by
} | Select-Object -Last 1
if (!$target) {throw 'No pending MERIT download to audit'}
& $py -m ceeprodgee status
if ($LASTEXITCODE -ne 0) {throw 'Status error'}
$fname=Join-Path (Join-Path $P 'downloads') $target.file
if (!(Test-Path $fname)) {
    Write-Host ('Download the completed export from Google Drive to: '+$fname)
    Write-Host ('Task key: '+$target.key)
    exit 2
}
& $py -m ceeprodgee audit --key $target.key --file $fname
if ($LASTEXITCODE -ne 0) {throw 'QC rejected output; do not submit another MERIT task'}
Write-Host ('QC_PASS: '+$target.key)
