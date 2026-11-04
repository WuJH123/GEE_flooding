param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$P=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261104'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
Set-Location $P;$env:PYTHONPATH=$P
& $PY -m ceeopt wc-compare --root $Root --reference-dir "$Root\gate_c_reference"
if ($LASTEXITCODE -ne 0){throw 'Independent online GEE Gate C comparison FAILED, prohibit global local extraction.'}
Write-Host 'GATE_C_LOCAL_VS_GEE_PASS' -ForegroundColor Green
