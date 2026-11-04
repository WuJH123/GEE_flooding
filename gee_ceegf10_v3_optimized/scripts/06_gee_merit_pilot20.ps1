param([string]$Root='E:\GEE_flooding')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104';$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m ceeopt merit-plan --block 20
if ($LASTEXITCODE -ne 0){throw 'MERIT full GF10 plan failed'}
# EXPLICIT single 20x20 EE task, not global.
& $PY -m ceeopt merit-pilot --execute --confirm CEE_GF10_OPTIMIZED_V3_20261104
if ($LASTEXITCODE -ne 0){throw 'MERIT 20x20 pilot submission failed'}
Write-Host 'Only MERIT 20x20 Wuhan pilot submitted. After SUCCEEDED download TIFF and audit.'
