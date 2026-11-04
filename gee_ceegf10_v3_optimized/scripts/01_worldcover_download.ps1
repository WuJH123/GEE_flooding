param([string]$Root='E:\WJH_CEE')
$ErrorActionPreference='Stop'
$PY=Join-Path $Root '.venv\Scripts\python.exe'
$folder=Join-Path $Root 'data\raw\esa_worldcover_2021\map'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$drive=[IO.Path]::GetPathRoot($Root)
$free=(Get-PSDrive -Name $drive.Substring(0,1)).Free
if ($free -lt 300GB) {throw 'At least 300 GiB free SSD recommended for 117GB Map download + working area. Do not touch other source data.'}
$aws=Join-Path $Root '.venv\Scripts\aws.exe'
if (-not (Test-Path $aws)){
  & $PY -m pip install awscli -i https://pypi.tuna.tsinghua.edu.cn/simple
  if ($LASTEXITCODE -ne 0){throw 'AWS CLI install failed; use official installer manually.'}
}
if (-not (Test-Path $aws)){throw "AWS CLI missing: $aws"}
Write-Host 'Downloading ONLY official ESA WorldCover v200/2021 Map (about 117GB), resumable; no GEE EECU.'
& $aws s3 sync s3://esa-worldcover/v200/2021/map $folder --no-sign-request --only-show-errors
if ($LASTEXITCODE -ne 0){throw 'Download incomplete; rerun same aws sync safely.'}
Write-Host 'ESA public Map transfer finished. Verify 2651 COGs with the next command.'
