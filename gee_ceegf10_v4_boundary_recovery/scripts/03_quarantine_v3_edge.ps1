. "$PSScriptRoot\00_environment.ps1"
& $PY -m cee_boundary_v4 quarantine --key 'merit_-1740_-240_10'
if($LASTEXITCODE -ne 0){throw 'Failed 3474x10 task not reconciled; stop'}
