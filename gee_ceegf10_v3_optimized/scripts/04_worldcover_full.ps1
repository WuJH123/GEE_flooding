param([string]$Root='E:\WJH_CEE',[int]$Workers=16)
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m ceeopt wc-full --root $Root --workers $Workers --confirm GF10_LOCAL_10M_FULL_20261104
if ($LASTEXITCODE -ne 0){throw 'Global WorldCover incomplete; successfully QC-passed blocks remain reusable.'}
& $PY -m ceeopt wc-verify --root $Root
if ($LASTEXITCODE -ne 0){throw '1,395,471-cell output did NOT pass; not publication-ready.'}
