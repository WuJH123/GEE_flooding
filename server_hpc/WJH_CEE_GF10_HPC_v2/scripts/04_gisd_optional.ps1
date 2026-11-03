$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$RARS=@(Get-ChildItem "$ROOT\CEE数据" -Filter 'GISD30_1985-2020_*.rar' -File)
if ($RARS.Count -ne 12) { Write-Warning "Found $($RARS.Count) RAR packages; verify expected 12 before global production" }
$dest="$ROOT\data\staged\gisd30_native_v1"
New-Item -Type Directory -Force $dest | Out-Null
$seven=Get-Command 7z,7za -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $seven) { throw 'Install 7-Zip or add 7z.exe to PATH to extract GISD30 RAR archives' }
foreach($rar in $RARS){
 & $seven.Source x -y "-o$dest" $rar.FullName '*.tif'
 if ($LASTEXITCODE -ne 0) { throw "RAR extraction failed $($rar.Name)" }
}
$nativeCount=@(Get-ChildItem $dest -Filter 'GISD30_1985-2020_*.tif' -Recurse).Count
Write-Host "GISD source tif count = $nativeCount (inventory previously observed 953; official reports 961; audit gaps)"
& $PY -m gf10hpc gisd-prep --source-dir $dest `
  --out "$ROOT\data\working\gisd30_binary_to_1km_v2" --workers 8 --gdal-threads 2 --max-files 8
if ($LASTEXITCODE -ne 0) { throw 'GISD binary staging pilot failed' }
Write-Host 'To run all native files, rerun without --max-files 8 after checking QC.'
