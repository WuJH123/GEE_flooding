# Figure1 publication contract (GEE_flooding independent paper) - NO DOWNLOADS
param(
 [string]$Root="E:\GEE_flooding",
 [string]$Tag="fig1_publication_v1",
 [string]$V3Tag="fig1_v3_full_r2",
 [string]$V2Tag="fig1_v2",
 [string]$Raw="E:\GEE_flooding\data\raw\groundsource_2026.parquet",
 [string]$West="E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s00.tif",
 [string]$East="E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s01.tif",
 [string]$CityPopulation="",
 [string]$PhysicalReviewed="",
 [string]$IndependentStormManifest="",
 [switch]$SkipSmoke
)
$ErrorActionPreference="Stop"
$PY=Join-Path $Root ".venv\Scripts\python.exe"
$GRID=Join-Path $Root "data\reference\grid10_urban_2020.parquet"
$LABEL=Join-Path $Root "outputs\labels\groundsource_gf10_primary.parquet"
$CITY=Join-Path $Root ("outputs\"+$V3Tag+"\ucdb_city_development_holdout.csv")
$CROSS=Join-Path $Root ("outputs\"+$V2Tag+"\fig1_grid_dominant_ucdb.parquet")
$EXTQC=Join-Path $Root ("outputs\"+$V3Tag+"\fig1_v3_qc.json")
foreach($p in @($PY,$Raw,$West,$East,$GRID,$LABEL,$CITY,$CROSS,$EXTQC)){
 if(-not (Test-Path -LiteralPath $p)){throw "Required prior local asset missing: $p"}
}
$base=Join-Path $Root ("outputs\"+$Tag)
if(Test-Path -LiteralPath $base){throw "Version exists: $base. Choose a new -Tag."}
function Invoke-Py([string[]]$Arguments){
 & $PY @Arguments
 if($LASTEXITCODE -ne 0){throw "Python failed: $($Arguments -join ' ')"}
}
Set-Location $Root
if(-not $SkipSmoke){
 Invoke-Py @("-m","pytest","-q","tests/test_fig1_publication.py")
}
Invoke-Py @("-m","gee_flooding","--root",$Root,"fig1-spatial-frame",
             "--core",$GRID,"--west",$West,"--east",$East,"--tag",$Tag)
Invoke-Py @("-m","gee_flooding","--root",$Root,"fig1-tier-audit",
             "--raw",$Raw,"--primary",$LABEL,"--tag",$Tag)
$cmd=@("-m","gee_flooding","--root",$Root,"fig1-paper","--tag",$Tag,
        "--spatial-dir",(Join-Path $base "grid"),
        "--tier-dir",(Join-Path $base "labels"),
        "--city-file",$CITY,"--crosswalk",$CROSS,"--v3-qc",$EXTQC)
if($CityPopulation){
 if(-not (Test-Path -LiteralPath $CityPopulation)){throw "Population CSV not found"}
 $cmd+=@("--city-population",$CityPopulation)
}
if($PhysicalReviewed){
 if(-not (Test-Path -LiteralPath $PhysicalReviewed)){throw "Reviewed physical CSV not found"}
 $cmd+=@("--physical-reviewed",$PhysicalReviewed)
}
if($IndependentStormManifest){
 if(-not (Test-Path -LiteralPath $IndependentStormManifest)){throw "Independent storm manifest missing"}
 $cmd+=@("--independent-storm-manifest",$IndependentStormManifest)
}
Invoke-Py $cmd
Get-Content (Join-Path $base "paper\figure1_publication_gate.json") -Raw
Write-Host "Five-panel draft: $base\paper" -ForegroundColor Green
Write-Warning "Figure1 is NOT publication-final unless all evidence gates have genuine external reviews."
