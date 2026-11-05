param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $py)) {throw 'Use original E:\GEE_flooding virtual environment'}
$env:PYTHONPATH=$P
& $py -m ceeprodgee preview-edge --x -1740 --y -240 --n 10
if ($LASTEXITCODE -ne 0) {throw 'Edge plan failed'}
Write-Host 'Expected edge_csv and 3 valid nonantarctic land cells (from 2026-11-05 audited report).'
