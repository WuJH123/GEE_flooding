. "$PSScriptRoot\00_environment.ps1"
& $PY -m cee_boundary_v4 status
if($LASTEXITCODE -ne 0){throw 'Could not query EE task status'}
