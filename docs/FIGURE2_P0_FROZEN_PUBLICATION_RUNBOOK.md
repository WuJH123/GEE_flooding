# Figure 2 P0: frozen publication evaluation, data requirements and Windows operations

Repository: WuJH123/GEE_flooding, the independent Communications Earth & Environment manuscript. This document concerns Figure 2 only. E:\Global_flooding is a READ-ONLY legacy source, not a writable folder and not the frozen GF10 research panel.

## What Figure 2 proves

Figure2a: Create an independently observed IMERG-exposed GF10 grid-day universe, freeze 2021–2023 Figure1-v3 eligible UCDB cities BEFORE seeing 2024–2025 news, then join the imperfect Groundsource positive reports. Unreported is UNLABELED, never monitored dry.

Figure2b: M0 weather; M1 plus HAND/slope; M2 plus land cover; M3 plus built spatial form; M4 plus historical GHSL growth; M5 is optional independently audited observation-propensity sensitivity, not true-risk correction. Compare identical heldout observations with paired meteorological-storm bootstrap delta PR-AUC vs M0, not unrelated intervals or only ROC-AUC.

Figure2c: Frozen development 2021–2023 and future 2024–2025 in (1) training-candidate cities and (2) genuinely withheld Figure1-v3 cities. Also cross-city 2021–2023 diagnostic. Strictly embargo meteorological storm IDs shared with training and ±7 calendar days at the 2023/24 year boundary. Report invalid test domains rather than falling back to random rows.

Figure2d: Distinguish news-proxy reliability and genuine independently observed pluvial flood positive plus observed-dry negative evidence. GFID/DFO/GFD catalogue agreement is not an observed-dry reference. In urban pluvial settings a Sentinel-1 non-detection is not proof of no flooding.

Figure2e: Terrain/surface nonlinearity and interaction are observational associations; not proof of drainage intervention causality.

## P0 priority order

1. Local file/schema inventory and frozen 10km reference, no new downloads; inspect Figure1 v3 development-only city flags and audited labels.
2. Check all static predictors, units, epochs and GF10 joins; freeze a geographically and climatically stratified city subset WITHOUT 2024-25 news.
3. Run one small authenticated GEE static, GHSL exposure, and weekly IMERG+ERA5-Land table task. Do not run giant global image exports or EPSG:6933 GEE raster reprojections.
4. Audit actual GEE CSV completeness: grid_id, UTC date, rainfall 48 half-hour observations/day and 336 prior 7 days, nonnegative features, missing/duplicate cells, native-era coverage. Successful dry runs are not data.
5. Process complete 2021–2025 selected cities; prepare one consistent full-period NEWS POSITIVE vs UNLABELED panel. Use fixed version tags and no-overwrite outputs.
6. Run training-only standardized logistic and gradient boosting M0–M4, paired storm-bootstrap delta and predeclared frozen prospective transfer.
7. Produce Figure2a–e and independent physical review. M5 only with externally audited propensity; full publication gate requires physically observed pluvial cases AND observed dry control intervals from valid monitoring coverage.
8. Geographic/seasonal/±1–3 day reporting-window/IMERG source-status and land-cover sensitivity, audit rainfall threshold 10/20/30 mm and storm radius 20/30/50 km, error-group summary.
9. Only after above: manuscript physical susceptibility claims or later exposure/fairness figures. If physical external validation fails, rename outcome to transferable flood NEWS REPORTING RESPONSE.

## Data catalogue and provenance

Already recorded locally (existence must still be verified):
- E:\GEE_flooding\data\reference\grid10_urban_2020.parquet: authoritative 10km EPSG:6933 frozen urban grid.
- E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet: geocoded Groundsource reported-news observations, not verified water.
- E:\GEE_flooding\outputs\fig1_v2\fig1_grid_dominant_ucdb.parquet: urban-centre crosswalk.
- E:\GEE_flooding\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv: only development-year city candidate classification; select newer audited version if it exists.
- E:\数据集 and E:\Global_flooding: raw GHSL, MERIT, urban land cover, WorldPop, IBTrACS, GRIP, GAIA, Koppen and reporting-selection candidates. Check grid scale and year; DO NOT reuse old 20km rows as GF10.
- E:\Global_flooding\grid10\gfd_physical_v3: historical satellite task files are only candidates, not verified measured inundation.

Need GEE extraction, not full local raw downloads:
- IMERG V07 NASA/GPM_L3/IMERG_V07: 30min precipitation rate mm/h, 0.5-hour integration; audit permanent/provisional product epoch.
- ERA5-Land ECMWF/ERA5_LAND/HOURLY: 24h antecedent soil-water/temperature; coarse native climate context, not street-scale sensor.
- MERIT Hydro MERIT/Hydro/v1_0_1: HAND, elevation, slope, upstream area, water.
- ESA/WorldCover/v200: 2021 class fractions, not measured real adaptation investment.
- JRC/GHSL/P2023A/GHS_BUILT_S/2000 and /2020, plus JRC/GHSL/P2023A/GHS_POP/2020: built form, population and historical growth. Verify GHSL population/area conservation against native reference.
- GLOBAL_FLOOD_DB/MODIS_EVENTS/V1: 2000–2018 MODIS historical context only, not contemporary 2021–2025 street-pluvial negatives.
Official references: https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07 and https://developers.google.com/earth-engine/guides/best_practices and https://developers.google.com/earth-engine/apidocs/export-table-todrive

## Windows PowerShell 0 — update and audit now, requires no Earth Engine submission

    Set-Location E:\GEE_flooding
    git status --short
    git fetch origin
    git pull --ff-only origin main
    $ROOT="E:\GEE_flooding"
    $PY="$ROOT\.venv\Scripts\python.exe"
    & $PY -m pip install -e ".[test]"
    & $PY -m pip install earthengine-api
    & $PY -m pytest -q
    & $PY -m gee_flooding.fig2_preflight --root $ROOT --city-audit-v3 "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_resilience --root $ROOT --tag fig2_inputs_v3_20261031

If git has uncommitted changes, review before pull; never hard reset. If the Figure1-v3 city audit uses a different output tag, pass its real path, NOT an all-year Figure1-v2 status.

## Windows 1 — freeze a geographic 10km pilot independent of news labels

    $G="$ROOT\data\reference\grid10_urban_2020.parquet"
    $F1="$ROOT\outputs\fig1_v2"
    & $PY -m gee_flooding.fig2_sampling --root $ROOT --grid $G --crosswalk "$F1\fig1_grid_dominant_ucdb.parquet" --cities "$F1\fig1_ucdb_city_sample_audit.csv" --city-audit-v3 "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv" --max-cities 40 --cells-per-city 12 --seed 42 --tag fig2_subset_v3
    $G2="$ROOT\data\reference\fig2_subset_v3\fig2_GF10_selected_grid.parquet"

This aims for around 480 cells in frozen Figure1-v3 development-eligible TRAIN and HELDOUT candidate cities. Eligibility uses 2021–2023 news only; 2024–2025 outcomes are excluded from sampling. The pilot is NOT a global probability sample.

## Windows 2 — dry-run bounded GEE table exports; submit only one controlled pilot

    & $PY -m gee_flooding.fig2_gee --grid $G2 --mode static --start-row 0 --count 20
    & $PY -m gee_flooding.fig2_gee --grid $G2 --mode exposure --start-row 0 --count 20
    & $PY -m gee_flooding.fig2_gee_weekly --grid $G2 --start 2024-07-01 --days 7 --start-row 0 --count 20

Authenticate local registered Earth Engine Cloud Project using earthengine executable:

    $EE="$ROOT\.venv\Scripts\earthengine.exe"
    & $EE authenticate
    & $EE set_project YOUR_EARTH_ENGINE_CLOUD_PROJECT
    $PROJECT="YOUR_EARTH_ENGINE_CLOUD_PROJECT"
    & $PY -m gee_flooding.fig2_gee --grid $G2 --mode static --start-row 0 --count 20 --project $PROJECT --submit
    & $PY -m gee_flooding.fig2_gee --grid $G2 --mode exposure --start-row 0 --count 20 --project $PROJECT --submit
    & $PY -m gee_flooding.fig2_gee_weekly --grid $G2 --start 2024-07-01 --days 7 --start-row 0 --count 20 --project $PROJECT --submit

Task submitted is NOT complete. Check https://code.earthengine.google.com/tasks and download matching COMPLETED CSVs from the Google Drive GEE_flooding_Figure2 folder. One-week bounded exports reduce task count by seven but are not a global resume scheduler; never automatically loop 166,414 × 1826 cell-days.

## Windows 3 — downloaded output layout

    New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_weather"
    New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_static"
    New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_exposure"

Place completed daily/weekly f2_weather*.csv in weather, f2_static*.csv in static, f2_exposure*.csv in exposure. Filename is part of the time/row QA. A single 7-day task is NOT a full 2021–2025 panel.

## Windows 4 — after the FULL declared 2021–2025 GF10 × day sample is downloaded

    $ACTUAL_COUNT=480
    & $PY -m gee_flooding.fig2_prepare --root $ROOT --grid $G2 --grid-cities "$F1\fig1_grid_dominant_ucdb.parquet" --weather-dir "$ROOT\data\gee_exports\fig2_weather" --static-dir "$ROOT\data\gee_exports\fig2_static" --exposure-dir "$ROOT\data\gee_exports\fig2_exposure" --start 2021-01-01 --end 2025-12-31 --start-row 0 --count $ACTUAL_COUNT --p24-min 20 --p3-min 10 --radius-km 30 --tag fig2_prepared_2021_2025_v1

    $DER="$ROOT\data\derived\fig2_prepared_2021_2025_v1"
    & $PY -m gee_flooding --root $ROOT panel --weather "$DER\storm_exposure_weather.parquet" --static "$DER\static_grid_factors.parquet" --labels "$ROOT\outputs\labels\groundsource_gf10_primary.parquet" --tag fig2_panel_2021_2025_v1

Replace ACTUAL_COUNT with the EXACT sample-qc cell count. In a 480-cell design, 1,826 days imply 876,480 full universe cell-days before rainfall filtering. The local builder enforces a 2-million-row cap and will abort incomplete/duplicated weather. Year-based storm splitting and weather structure still need dedicated sensitivity checks before the manuscript.

## Windows 5 — frozen future/city evaluation plus original five panel news-proxy plot

    $PANEL="$ROOT\outputs\panels\fig2_panel_2021_2025_v1\storm_exposure_with_news_labels.parquet"
    $AUDIT="$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_frozen --root $ROOT --panel $PANEL --city-audit-v3 $AUDIT --weather-contract "$DER\fig2_weather_provenance.json" --tag fig2_frozen_2021_2025_v1
    & $PY -m gee_flooding.fig2 --root $ROOT --panel $PANEL --contract "$DER\fig2_weather_provenance.json" --extended "$DER\fig2_extended_grid_factors.parquet" --resilience-static "$DER\fig2_resilience_all_static_GF10.parquet" --grid-cities "$F1\fig1_grid_dominant_ucdb.parquet" --cities "$F1\fig1_ucdb_city_sample_audit.csv" --tag fig2_news_proxy_2021_2025_v1

Two output directories are immutable. The first contains frozen-model metrics, storm-paired PR-AUC changes, heldout predictions and gates; the second contains the existing five-panel NEWS PROXY plot. Neither proves genuine pluvial flood susceptibility.

## Publication-level physical validation

The optional current validator needs CSV columns grid_id,date,sensor,valid_observation,flood_observed,source_independent,pluvial_confirmed and independently reviewed original evidence. Obtain verified sensor-observed pluvial flooding AND monitored dry periods, with spatial/temporal coverage. CEMS GFM/UNOSAT cases are supplementary physical evidence where a satellite actually observed; radar non-detection/obstruction is NOT a negative. GFID/GFD/DFO event catalogues are not independent water measurements.

Run with the existing Figure2 --physical and --require-physical flags only when that CSV has been independently reviewed; otherwise label Figure2 as transferable news-report response model.

Remaining P0: real GEE end-to-end success, detailed native pixel/area conservation, cloud task manifest/resume at year/region scale, full 2021–2025 exposure completeness, externally observed positive/dry verification, temporal ±1/±3 day shift, rain/storm thresholds, climate/country and observation selection sensitivity. Never mark these as PASS using synthetic GitHub Actions.
