param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop';$P=Split-Path -Parent $PSScriptRoot
$py=Join-Path $Root '.venv\Scripts\python.exe';$env:PYTHONPATH=$P
& $py -m ceeprodgee merge --family merit
if ($LASTEXITCODE -ne 0) {throw 'GeoTIFF + edge CSV merge failed QC'}
Write-Host 'Partial GF10 Parquet generated. DO NOT treat it as all-global until all 1395471 GF10 IDs covered and provenance complete.'
