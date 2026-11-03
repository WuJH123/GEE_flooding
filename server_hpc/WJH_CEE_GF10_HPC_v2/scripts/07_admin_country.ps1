$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$archive="$ROOT\CEE数据\geoBoundariesCGAZ_ADM0.zip"
$dest="$ROOT\data\staged\geoboundaries_adm0_v1"
& $PY -m gf10hpc stage-archive --zip $archive --out $dest
if ($LASTEXITCODE -ne 0) {throw 'Administrative archive corrupt or previously modified'}
$shp=@(Get-ChildItem $dest -Recurse -Filter '*.shp')
if ($shp.Count -ne 1) {throw 'Verify shapefile contents manually'}
& $PY -m gf10hpc vector-centroid --source $shp[0].FullName --field shapeGroup `
 --out "$ROOT\data\derived\gf10_country_centroid_proxy_v2.parquet" --batch 100000
if ($LASTEXITCODE -ne 0) {throw 'Country centroid assignment failed'}
Write-Warning 'Centroid country is a convenience proxy, not largest land-overlap country for coastal/island cells.'
