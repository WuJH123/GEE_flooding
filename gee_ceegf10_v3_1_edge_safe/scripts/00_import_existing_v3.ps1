param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$Old=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105'
$py=Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $py)) {$py=Join-Path $Old '.venv\Scripts\python.exe'}
if (!(Test-Path $py)) {throw "Original Python environment unavailable: $py"}
$from=Join-Path $Old 'config\production.json'
$fromLedger=Join-Path $Old 'reports\task_ledger.json'
$to=Join-Path $P 'config\production.json'
$toLedger=Join-Path $P 'reports\task_ledger.json'
if (!(Test-Path $from) -or !(Test-Path $fromLedger)) {throw 'Original v3 config/ledger missing; no task state can be invented'}
if ((Test-Path $to) -or (Test-Path $toLedger)) {
  if (!(Test-Path $to) -or !(Test-Path $toLedger)) {throw 'Only one migration file exists; inspect before proceeding'}
  $oldC=Get-Content -LiteralPath $from -Raw | ConvertFrom-Json
  $newC=Get-Content -LiteralPath $to -Raw | ConvertFrom-Json
  if ($oldC.project -ne $newC.project -or $oldC.grid_sha256 -ne $newC.grid_sha256 -or
      $oldC.run_id -ne $newC.run_id) {
    throw 'Existing destination state refers to another Cloud project, frozen GF10 or run ID'
  }
  Write-Host 'STATE_ALREADY_INITIALIZED. Current ledger may include new repair tasks; it will NEVER be overwritten.'
} else {
  Copy-Item -LiteralPath $from -Destination $to
  Copy-Item -LiteralPath $fromLedger -Destination $toLedger
  Write-Host 'FROZEN_V3_LEDGER_COPIED_WITHOUT_MODIFICATION'
  # Copy only locally approved legacy results. Preserve original checksum.
  $records=Get-Content -LiteralPath $fromLedger -Raw | ConvertFrom-Json
  $oldDownloads=Join-Path $Old 'downloads'
  $newDownloads=Join-Path $P 'downloads'
  foreach($r in $records) {
    if ($r.local_qc_pass -eq $true -and $r.file) {
      $a=Join-Path $oldDownloads $r.file
      $b=Join-Path $newDownloads $r.file
      if (Test-Path -LiteralPath $a) {
        Copy-Item -LiteralPath $a -Destination $b
        if ((Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash) {
            throw ('Approved source raster changed during migration: '+$r.file)
        }
      } else {
        Write-Warning ('QC-approved legacy output not present in old downloads; manually restore later: '+$r.file)
      }
    }
  }
}
$env:PYTHONPATH=$P
Push-Location $P
try {
  & $py -m pytest -q tests
  if ($LASTEXITCODE -ne 0) {throw 'Offline regression tests failed'}
  & $py -m ceeprodgee verify
  if ($LASTEXITCODE -ne 0) {throw 'Frozen source verification failed'}
} finally {Pop-Location}
Write-Host 'PREPARE_PASS. The original v3 code, accepted Wuhan output and task ledger were NOT modified.'
