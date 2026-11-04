param([string]$Root='E:\WJH_CEE',[int]$Workers=8)
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m ceeopt wc-index --root $Root --full
if ($LASTEXITCODE -ne 0){throw 'ESA 2021 COG source incomplete or source projection invalid'}
& $PY -m ceeopt wc-pilot --root $Root --workers $Workers
if ($LASTEXITCODE -ne 0){throw 'Four-block native10m pilot failed: preserve QC and do not launch global'}
& $PY -m ceeopt wc-verify --root $Root --partial
if ($LASTEXITCODE -ne 0){throw 'Pilot class/land values failed QA'}
Write-Host 'Copy FOUR independent Gate C mosaics from GEE_flooding/gee_ceegf10_v1/reports/gate_c_mosaics into E:\WJH_CEE\gate_c_reference, then run 03.'
