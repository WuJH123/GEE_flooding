param([string]$Root='E:\GEE_flooding',
      [ValidateSet('gcs','drive')][string]$Storage='drive',
      [string]$Bucket='',
      [Parameter(Mandatory=$true)][double]$MonthUsedEecu,
      [double]$BudgetLimitEecu=900,
      [int]$MaxInflight=4)
$ErrorActionPreference='Stop'
$Pkg=Join-Path $Root 'CEE_GF10_GLOBAL_EE_V8_20261106'
$Py=Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH="$Pkg;$(Join-Path $Root 'CEE_GF10_EFFICIENT_V3_20261105')"
$cmd=@('-m','cee_v8','--root',$Root,'--pkg',$Pkg,'run','--storage',$Storage,
 '--max-inflight',"$MaxInflight",'--month-used-eecu',"$MonthUsedEecu",
 '--budget-limit-eecu',"$BudgetLimitEecu",'--execute','--confirm','CEE_GF10_GLOBAL_EE_V8_20261106')
if($Storage -eq 'gcs'){
 if([string]::IsNullOrWhiteSpace($Bucket)){throw 'Existing authorized Cloud Storage Bucket is required for GCS'}
 $cmd+=@('--bucket',$Bucket)
}
& $Py @cmd
if($LASTEXITCODE -ne 0){throw 'V8 controller exited with error; read sqlite ledger, repair then restart same command'}
