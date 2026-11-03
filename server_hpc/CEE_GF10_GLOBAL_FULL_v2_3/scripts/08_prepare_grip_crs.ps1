param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PKG=Split-Path -Parent $PSScriptRoot
$PY=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PKG
Set-Location $PKG
& $PY -c "from pathlib import Path; from ceeall.raster import ensure_grip4_georeference; r=Path(r'$Root'); p=r/'data/staged/cee_all/GRIP4_density_total/grip4_total_dens_m_km2.asc'; result=ensure_grip4_georeference(r,p,'grip-density'); print('GRIP4_CRS_OK',result['metadata_after']['crs'],result['prj_sha256'])"
if($LASTEXITCODE -ne 0){ throw 'GRIP4 source CRS repair failed; do not start full global compute.' }
Write-Host 'GRIP4 5-arcminute WGS84 metadata verified and staged sidecar available.' -ForegroundColor Green
