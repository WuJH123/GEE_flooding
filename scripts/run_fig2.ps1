# Figure 2 Windows entry point. DOES NOT download, submit GEE tasks or modify old repo.
[CmdletBinding()]
param(
    [ValidateSet("preflight","prepare","train")][string]$Phase="preflight",
    [string]$Root="E:\GEE_flooding",
    [string]$Fig1Tag="fig1_v2",
    [string]$GridPath="",
    [string]$ExposureDir="",
    [string]$Tag="fig2_v1",
    [string]$Start="2023-08-01",
    [string]$End="2023-08-31",
    [int]$StartRow=0,
    [int]$Count=50,
    [string]$WeatherDir="",
    [string]$StaticDir="",
    [string]$Physical="",
    [switch]$RequirePhysical
)
$ErrorActionPreference="Stop"
$PY=Join-Path $Root ".venv\Scripts\python.exe"
$GRID=Join-Path $Root "data\reference\grid10_urban_2020.parquet"
if($GridPath){$GRID=$GridPath}
$LABEL=Join-Path $Root "outputs\labels\groundsource_gf10_primary.parquet"
$F1=Join-Path $Root ("outputs\"+$Fig1Tag)
$CITIES=Join-Path $F1 "fig1_ucdb_city_sample_audit.csv"
$CROSSWALK=Join-Path $F1 "fig1_grid_dominant_ucdb.parquet"
if(-not $WeatherDir){$WeatherDir=Join-Path $Root "data\gee_exports\fig2_weather"}
if(-not $StaticDir){$StaticDir=Join-Path $Root "data\gee_exports\fig2_static"}
$WEATHER=Join-Path $Root "data\derived\storm_exposure_weather.parquet"
$STATIC=Join-Path $Root "data\derived\static_grid_factors.parquet"
$EXTENDED=Join-Path $Root "data\derived\fig2_extended_grid_factors.parquet"
$CONTRACT=Join-Path $Root "data\derived\fig2_weather_provenance.json"
$RESILIENCE=Join-Path $Root "data\derived\fig2_resilience_all_static_GF10.parquet"
$PANEL=Join-Path $Root "outputs\panels\storm_exposure_with_news_labels.parquet"
$paths=@($PY,$GRID,$LABEL,$CITIES,$CROSSWALK,$WEATHER,$STATIC,$EXTENDED,$CONTRACT,$PANEL,$RESILIENCE)
Write-Host ("Figure2 Phase={0}; NO automatic downloads/exports; root={1}" -f $Phase,$Root) -ForegroundColor Cyan
foreach($p in $paths){Write-Host ("{0} {1}" -f $(if(Test-Path -LiteralPath $p){"EXISTS "}else{"MISSING"}),$p)}
if($Phase -eq "preflight"){exit 0}
foreach($p in @($PY,$GRID,$LABEL,$CITIES,$CROSSWALK)){
    if(-not (Test-Path -LiteralPath $p)){throw "Required baseline is missing: $p"}
}
if($Phase -eq "prepare"){
    $argsPrepare=@("-m","gee_flooding.fig2_prepare","--root",$Root,
          "--grid",$GRID,"--grid-cities",$CROSSWALK,
          "--weather-dir",$WeatherDir,"--static-dir",$StaticDir,
          "--start",$Start,"--end",$End,"--start-row",$StartRow,"--count",$Count)
    if($ExposureDir){$argsPrepare+=@("--exposure-dir",$ExposureDir)}
    & $PY @argsPrepare
    if($LASTEXITCODE -ne 0){throw "Figure2 prepare failed"}
    & $PY -m gee_flooding --root $Root panel --weather $WEATHER --static $STATIC --labels $LABEL
    if($LASTEXITCODE -ne 0){throw "Figure2 panel failed"}
    Write-Host "Weather & panel contracts complete. Run -Phase train when enough positives/groups exist."
    exit 0
}
foreach($p in @($WEATHER,$STATIC,$EXTENDED,$CONTRACT,$PANEL)){
    if(-not (Test-Path -LiteralPath $p)){throw "Cannot fit Figure2; missing $p"}
}
$argsList=@("-m","gee_flooding.fig2","--root",$Root,"--panel",$PANEL,
            "--contract",$CONTRACT,"--extended",$EXTENDED,
            "--grid-cities",$CROSSWALK,"--cities",$CITIES,"--tag",$Tag)
if(Test-Path -LiteralPath $RESILIENCE){$argsList+=@("--resilience-static",$RESILIENCE)}
if($Physical){$argsList+=@("--physical",$Physical)}
if($RequirePhysical){$argsList+=@("--require-physical")}
& $PY @argsList
if($LASTEXITCODE -ne 0){throw "Figure2 train/plot failed"}
Write-Host "Figure2 output: $(Join-Path $Root ('outputs\'+$Tag))" -ForegroundColor Green
