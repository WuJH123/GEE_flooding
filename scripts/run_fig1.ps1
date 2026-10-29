# GEE_flooding standalone Figure 1 — no downloads and no GEE task submissions.
param(
 [string]$Root="E:\GEE_flooding",
 [string]$Tag="fig1_v1",
 [switch]$SkipGFID,
 [switch]$SkipKoppen,
 [switch]$SkipWorld
)
$ErrorActionPreference="Stop"
$PY=Join-Path $Root ".venv\Scripts\python.exe"
$GRID=Join-Path $Root "data\reference\grid10_urban_2020.parquet"
$LABEL=Join-Path $Root "outputs\labels\groundsource_gf10_primary.parquet"
$QC=Join-Path $Root "reports\qc\labels_qc.json"
$UCDB="E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg"
$GFID="E:\Global_flooding\grid10\reference_external\GFID\AggregatedFloodData.xlsx"
$KOPPEN="E:\Global_flooding\koppen_geiger_tif\1991_2020\koppen_geiger_0p1.tif"
$WORLD="E:\Global_flooding\grid10\fig1_public\natural_earth\ne_110m_admin_0_countries.shp"
foreach($p in @($PY,$GRID,$LABEL,$QC,$UCDB)){
 if(-not (Test-Path -LiteralPath $p)){throw "Required input missing: $p"}
}
$argsList=@(
  "-m","gee_flooding","--root",$Root,"fig1",
  "--grid",$GRID,"--labels",$LABEL,"--label-qc",$QC,
  "--ucdb",$UCDB,"--tag",$Tag,
  "--city-min-reports","5","--city-min-years","3"
)
if(-not $SkipGFID){
 if(-not (Test-Path $GFID)){throw "GFID Excel missing: $GFID. Use -SkipGFID only for provisional draft"}
 $argsList+=@("--gfid",$GFID)
}
if(-not $SkipKoppen){
 if(-not (Test-Path $KOPPEN)){throw "Koppen raster missing: $KOPPEN. Use -SkipKoppen only for provisional draft"}
 $argsList+=@("--koppen",$KOPPEN)
}
if(-not $SkipWorld){
 if(-not (Test-Path $WORLD)){throw "Natural Earth SHP missing: $WORLD. Use -SkipWorld only for provisional draft"}
 $argsList+=@("--world",$WORLD)
}
Write-Host "Running Figure1 with existing local sources; NO downloads" -ForegroundColor Cyan
& $PY @argsList
if($LASTEXITCODE -ne 0){throw "Figure1 failed with exit code $LASTEXITCODE"}
$dir=Join-Path $Root ("outputs\"+$Tag)
Write-Host "Figure1 saved: $dir" -ForegroundColor Green
Get-Content (Join-Path $dir "fig1_qc_and_provenance.json")
