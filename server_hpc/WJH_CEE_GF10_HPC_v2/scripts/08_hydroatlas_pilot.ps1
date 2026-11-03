$ErrorActionPreference='Stop'
$ROOT='E:\WJH_CEE';$PKG=Split-Path -Parent $PSScriptRoot;$PY="$ROOT\.venv\Scripts\python.exe";$env:PYTHONPATH=$PKG
$archive="$ROOT\CEE数据\BasinATLAS_Data_v10.gdb.zip"
$dest="$ROOT\data\staged\basinatlas_v10"
& $PY -m gf10hpc stage-archive --zip $archive --out $dest --max-gb 15
if ($LASTEXITCODE -ne 0) {throw 'BasinATLAS ZIP source or output QC failed'}
$gdb=@(Get-ChildItem $dest -Recurse -Directory -Filter '*.gdb')
if ($gdb.Count -ne 1) {throw 'Missing or ambiguous FileGDB directory'}
& $PY -c "import pyogrio; print(pyogrio.list_layers(r'$($gdb[0].FullName)'))"
# Only a modelled basin identifier PROXY, not GF10 native HAND or upstream cell area.
# Confirm the selected layer/field name from the printed list before enabling:
# & $PY -m gf10hpc vector-centroid --source $gdb[0].FullName `
#   --layer BasinATLAS_v10_lev06 --field HYBAS_ID --extra UP_AREA SUB_AREA `
#   --out "$ROOT\data\derived\basinatlas_lev06_centroid_v2.parquet"
