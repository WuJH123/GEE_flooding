# Run after cloud exports have appeared in Drive. Never starts a GEE task.
$ErrorActionPreference = 'Stop'
$P = Split-Path -Parent $MyInvocation.MyCommand.Path
$PY = 'E:\GEE_flooding\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PY)) { throw "Python environment missing: $PY" }
while ($true) {
    $result = & $PY "$P\merit_hybrid_runner.py" audit --batch-limit 100 | Out-String | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'MERIT QC command failed' }
    $failed = @($result.results | Where-Object { $_.state -eq 'QC_FAIL' })
    if ($failed.Count -gt 0) { throw "MERIT QC rejected $($failed[0].task_key): $($failed[0].error)" }
    $passed = @($result.results | Where-Object { $_.state -eq 'QC_PASS' }).Count
    Write-Host "New MERIT QC_PASS tasks in this batch: $passed"
    if ($passed -eq 0) { break }
}
& $PY "$P\assemble_merit_hybrid_v10.py"
if ($LASTEXITCODE -ne 0) { throw 'MERIT assembly failed' }
