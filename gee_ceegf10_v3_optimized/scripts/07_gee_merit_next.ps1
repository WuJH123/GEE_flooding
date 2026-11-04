param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104';$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m ceeopt merit-next --block 20 --execute --confirm CEE_GF10_OPTIMIZED_V3_20261104
if ($LASTEXITCODE -ne 0){throw 'MERIT next batch denied. Check previous task EECU, downloaded TIFF and QC.'}
