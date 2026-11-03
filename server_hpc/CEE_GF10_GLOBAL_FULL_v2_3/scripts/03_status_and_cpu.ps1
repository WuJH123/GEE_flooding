param([string]$Root='E:\WJH_CEE')
$path="$Root\reports\cee_full_v2\resource_monitor.csv"
if(Test-Path $path){
  Import-Csv $path | Select-Object -Last 15 | Format-Table -AutoSize
}else{ Write-Host 'Production monitor not started yet' }
Write-Host 'Current Python process count and memory:'
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Select-Object ProcessId,CommandLine | Format-Table -Wrap
Write-Host 'Performance bottleneck: compare CPU %, disk read/write MB and memory; never infer speed from utilization alone.'
