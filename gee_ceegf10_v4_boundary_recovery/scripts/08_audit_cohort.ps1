param([string]$Events='E:\GEE_flooding\data\frozen\case_control_gf10_dates.parquet')
. "$PSScriptRoot\00_environment.ps1"
& $PY -m cee_boundary_v4 cohort-check --events $Events
if($LASTEXITCODE -ne 0){throw 'Event case-control cohort does not meet required provenance/pairing contract; do not submit IMERG/ERA5 production'}
