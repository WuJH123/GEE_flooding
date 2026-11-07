# Recover only the 14 immutable seam parents from Earth Engine native pixels.
# Never starts an Earth Engine batch task, and never overwrites an audited parent.
$ErrorActionPreference = 'Stop'
$P = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = 'E:\GEE_flooding'
$PY = "$ROOT\.venv\Scripts\python.exe"
$parents = Import-Csv "$ROOT\CEE_GF10_GEE_RECOVERY_V4_20261105\plans\merit_quarantine_v4.csv"
if ($parents.Count -ne 14) { throw 'Expected exactly 14 frozen seam parents' }
foreach ($parent in $parents) {
    $key = $parent.tile_key
    $audit = Join-Path $P "merit_seam_exact_parents\$key\audit.json"
    if (Test-Path -LiteralPath $audit) {
        Write-Host "Existing seam audit preserved: $key"
        continue
    }
    & $PY "$P\seam_exact_parent_v10.py" --tile-key $key
    if ($LASTEXITCODE -ne 0) { throw "Seam source-pixel QC stopped: $key" }
}
