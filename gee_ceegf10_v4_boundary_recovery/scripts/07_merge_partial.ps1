. "$PSScriptRoot\00_environment.ps1"
& $PY -m cee_boundary_v4.merge
if($LASTEXITCODE -ne 0){throw 'Strict source registry merge rejected'}
