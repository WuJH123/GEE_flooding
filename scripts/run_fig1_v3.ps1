# Figure 1 v3 — CEE/GEE_flooding only. NO downloads and NO Earth Engine jobs.
param(
 [string]$Root="E:\GEE_flooding",
 [string]$Tag="fig1_v3",
 [string]$V2Tag="fig1_v2",
 [string]$GFID="E:\Global_flooding\grid10\reference_external\GFID\AggregatedFloodData.xlsx",
 [string]$Duplicates="E:\Global_flooding\grid10\reference_external\GFID\Potential_Duplicate_Events.csv",
 [string]$World="E:\Global_flooding\grid10\fig1_public\natural_earth\ne_110m_admin_0_countries.shp",
 [string]$PhysicalTable="",
 [string]$ReviewerTable="",
 [switch]$Fast
)
$ErrorActionPreference="Stop"
$PY=Join-Path $Root ".venv\Scripts\python.exe"
$GRID=Join-Path $Root "data\reference\grid10_urban_2020.parquet"
$LABELS=Join-Path $Root "outputs\labels\groundsource_gf10_primary.parquet"
$QC=Join-Path $Root "reports\qc\labels_qc.json"
$V2=Join-Path $Root ("outputs\"+$V2Tag)
foreach($p in @($PY,$GRID,$LABELS,$QC,$GFID,
                (Join-Path $V2 "fig1_grid_dominant_ucdb.parquet"),
                (Join-Path $V2 "fig1_ucdb_city_sample_audit.csv"))){
 if(-not (Test-Path -LiteralPath $p)){throw "Required local source missing: $p"}
}
if(Test-Path -LiteralPath (Join-Path $Root ("outputs\"+$Tag))){
 throw "Output version $Tag already exists. Use a fresh -Tag to avoid overwrite."
}
$CLI=@("-m","gee_flooding","--root",$Root,"fig1-v3",
       "--grid",$GRID,"--labels",$LABELS,"--label-qc",$QC,
       "--v2-dir",$V2,"--gfid",$GFID,"--tag",$Tag)
if($Duplicates -and (Test-Path -LiteralPath $Duplicates)){
 $CLI+=@("--gfid-duplicates",$Duplicates)
}else{
 Write-Warning "Potential-duplicate screening table unavailable; source-family deduplication not established"
}
if($World -and (Test-Path -LiteralPath $World)){
 $CLI+=@("--world",$World)
}else{
 Write-Warning "Country border absent: Unknown UCDB continent may remain unresolved"
}
if($PhysicalTable){
 if(-not (Test-Path -LiteralPath $PhysicalTable)){throw "Physical table does not exist: $PhysicalTable"}
 $CLI+=@("--physical",$PhysicalTable)
}
if($ReviewerTable){
 if(-not (Test-Path -LiteralPath $ReviewerTable)){throw "Human review table does not exist: $ReviewerTable"}
 $CLI+=@("--reviewer-table",$ReviewerTable)
}
if($Fast){
 $CLI+="--fast"
 Write-Warning "FAST GFID match is only on the first 1000 high grid-days. DO NOT REPORT ITS CONCORDANCE IN A PAPER."
}
Write-Host "No-download Figure1_v3 $Tag starting — all output under $Root" -ForegroundColor Cyan
& $PY @CLI
if($LASTEXITCODE -ne 0){throw "Figure 1 v3 execution failed: $LASTEXITCODE"}
$OUTPUT=Join-Path $Root ("outputs\"+$Tag)
Get-Content (Join-Path $OUTPUT "fig1_v3_qc.json") -Raw
Write-Host "Completed Figure1_v3 $OUTPUT" -ForegroundColor Green
