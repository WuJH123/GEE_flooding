. "$PSScriptRoot\00_environment.ps1"
Push-Location $PKG
try {
 & $PY -m pytest tests -q -W error
 if($LASTEXITCODE -ne 0){throw 'Boundary V4 unit tests failed, no EE allowed'}
 & $PY -m cee_boundary_v4 inspect
 if($LASTEXITCODE -ne 0){throw 'Frozen GF10 plan invalid'}
 Write-Host 'PRE-FLIGHT PASSED; no Earth Engine task submitted'
} finally { Pop-Location }
