param(
  [string]$Root='E:\WJH_CEE',
  [switch]$Execute
)
$ErrorActionPreference='Stop'
$Target=Join-Path $Root 'data\raw\ESA_WorldCover_2021_v200_COG'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
$AWS=Get-Command aws -ErrorAction SilentlyContinue
if(-not $AWS){ throw 'AWS CLI not found. Install from https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html' }
$Drive=(Get-Item $Root).PSDrive
$Free=[math]::Round((Get-PSDrive -Name $Drive.Name).Free/1GB,1)
Write-Host "Available storage $Free GB (ESA COG originals about 117 GB plus disk workspace)"
if($Free -lt 250){ throw 'At least 250 GB free recommended to keep source and processing workspace; not enough.' }
$Src='s3://esa-worldcover/v200/2021/map'
if(-not $Execute){
 Write-Host 'DRY RUN: Would download official ESA WorldCover 2021 COGs to ' $Target
 & aws s3 sync $Src $Target --no-sign-request --dryrun
} else {
 & aws s3 sync $Src $Target --no-sign-request --only-show-errors
 if($LASTEXITCODE -ne 0){throw 'Official ESA 2021 AWS download not complete'}
 Write-Host 'ESA source download sync finished. Source raster inventory/CRC still requires local QA.'
}
