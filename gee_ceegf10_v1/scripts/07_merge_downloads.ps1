param([ValidateSet('merit','worldcover')][string]$Family='merit')
$ErrorActionPreference='Stop'
$ROOT=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $ROOT '.venv\Scripts\python.exe'
$env:PYTHONPATH=$ROOT
# After *all* 12 COG GeoTIFF strips have been downloaded into data/downloads/$Family.
& $PY -m ceegee merge-static --family $Family
if ($LASTEXITCODE -ne 0) { throw 'Full GF10 raster join incomplete or failed scientific/QC gate' }
