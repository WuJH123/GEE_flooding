# Current no-download continuation (2026-10-29)

The local data are ALREADY present: original Groundsource 2,646,302; new GF10 166,414; mapped labels 2,202,651 (high 1,788,759). Run `inventory` and `summarize-labels` **only**; neither downloads nor overwrites existing labels. Outputs under E:\GEE_flooding\reports. Historic 20-km GHSL/M3 climate/static products can be viewed and audited, but are NOT grid-compatible with new 10-km training. Complete new 10km weather exposures and static terrain features remain missing. Old local directory E:\Global_flooding is read-only.

# Windows runbook — ALL new outputs E:\GEE_flooding

## First local setup (PowerShell)
1. git clone https://github.com/WuJH123/GEE_flooding.git E:\GEE_flooding
2. Set-Location E:\GEE_flooding
3. py -3.11 -m venv .venv
4. $PY = "E:\GEE_flooding\.venv\Scripts\python.exe"
5. & $PY -m pip install -e ".[test]"
6. & $PY -m pytest -q
7. & $PY -m gee_flooding --root "E:\GEE_flooding" init
8. & $PY -m gee_flooding --root "E:\GEE_flooding" inventory
9. & $PY -m gee_flooding --root "E:\GEE_flooding" summarize-labels

**Current user run (2026-10-29): original Zenodo dataset, GF10 bootstrap, and initial labels audit already finished. DO NOT re-download or rerun Stage 1–4.**

The raw file is now E:\GEE_flooding\data\raw\groundsource_2026.parquet, verified with Zenodo MD5.

## Independent grid freeze inside this new project
Read the two existing SMOD TIFFs in the old project (read-only). Write a fresh 10 km grid and QC exclusively to E:\GEE_flooding:

& $PY -m gee_flooding --root E:\GEE_flooding bootstrap-grid --west E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s00.tif --east E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s01.tif

Outputs: E:\GEE_flooding\data\reference\grid10_urban_2020.parquet and grid10_qc.json, with PASS_10KM_GRID_CONTRACT.

## Execute independent event audit (one PowerShell line)
& $PY -m gee_flooding --root E:\GEE_flooding labels --raw E:\GEE_flooding\data\raw\groundsource_2026.parquet --grid E:\GEE_flooding\data\reference\grid10_urban_2020.parquet --grid-qc E:\GEE_flooding\data\reference\grid10_qc.json --batch-size 10000

QC: E:\GEE_flooding\reports\qc\labels_qc.json.
Products: E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet and geocode_event_audit.parquet.

## Delayed supervised smoke — NOT ready until new independent inputs exist
Weather parquet E:\GEE_flooding\data\derived\storm_exposure_weather.parquet must cover all storm-exposed city grid-days, with grid_id,date,storm_id,city_id,rain_24h_mm,rain_3h_mm,api_7d_mm.
Static parquet E:\GEE_flooding\data\derived\static_grid_factors.parquet must have unique grid_id,hand_m,slope_deg,urban_fraction_2020,vegetation_fraction.

& $PY -m gee_flooding --root E:\GEE_flooding panel --weather E:\GEE_flooding\data\derived\storm_exposure_weather.parquet --static E:\GEE_flooding\data\derived\static_grid_factors.parquet --labels E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet

& $PY -m gee_flooding --root E:\GEE_flooding baseline --panel E:\GEE_flooding\outputs\panels\storm_exposure_with_news_labels.parquet

Baseline output: E:\GEE_flooding\outputs\models\baseline_ablation_metrics.csv and reports\qc\baseline_model_qc.json. This is a NEWS proxy, not confirmed actual flood prediction.

STOP on missing raw five-field schema, failing grid QC, broad geocodes, multiple storm IDs per grid-day, missing predictors, rare positives in heldout test, or existing outputs. Do NOT copy the old 20 km case-control labels into training.
