param([string]$Root='E:\GEE_flooding',[int]$Candidates=4)
$ErrorActionPreference='Stop';$P=Split-Path $PSScriptRoot -Parent
$Py=Join-Path $Root '.venv\Scripts\python.exe'
if(-not(Test-Path $Py)) {$Py=Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'}
$env:PYTHONPATH="$P;$(Join-Path $Root 'CEE_GF10_V6_SCIENCE_COHORT_20261105');$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
& $Py -m cee_v7 --root $Root cohort-plan --per-case $Candidates
if($LASTEXITCODE -ne 0){throw 'Candidate calendar plan blocked'}
& $Py -m cee_v7 --root $Root weather-preflight
if($LASTEXITCODE -ne 0){throw 'Weather science preflight blocked'}
