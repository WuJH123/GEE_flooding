$ROOT='E:\WJH_CEE';$dirs=Get-ChildItem "$ROOT\data\derived" -Directory -ErrorAction SilentlyContinue
$rows=@(foreach($dir in $dirs) {
 $qc=Join-Path $dir.FullName 'run_qc.json'
 if (Test-Path $qc) {
  $j=Get-Content $qc -Raw | ConvertFrom-Json
  [pscustomobject]@{Product=$dir.Name;Status=$j.status;Tiles=$j.n_tasks;Written=$j.n_written;Reused=$j.n_reused;Seconds=$j.elapsed_s;Exact=$j.method}
 }
}); $rows | Format-Table -AutoSize
