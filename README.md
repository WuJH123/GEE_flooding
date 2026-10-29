# GEE_flooding — independent global urban flood susceptibility research

**Separate project** from [Global_flooding](https://github.com/WuJH123/Global_flooding). All new results must live under **E:\GEE_flooding**. Old datasets can be read as immutable inputs; never write to old project directories.

## Scientific aim
Learn how terrain, land-cover and rainfall characterize **news-reported** urban floods, while quantifying geocoding uncertainty, reporting bias and generalization to unseen cities and storms. The long-term goal is independently validated urban *pluvial* flood susceptibility for a Communications Earth & Environment submission. A news report is NOT an inundation footprint; an unreported city-day is NOT flood-free.

## Source
Groundsource v1: https://doi.org/10.5281/zenodo.18647054 — original five columns uuid, geometry (WKB), area_km2 (geocoder polygon size, NOT inundation extent), start_date, end_date. 2020 GF10 frozen grid (EPSG:6933) is a READ-ONLY reference from the old repository. The 20 km historical case/control parquet is NOT valid as original source.

## Local setup (PowerShell)
    git clone https://github.com/WuJH123/GEE_flooding.git E:\GEE_flooding
    Set-Location E:\GEE_flooding
    py -3.11 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[test]"
    .\.venv\Scripts\python.exe -m pytest -q
    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding init
    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding download

## First production command: geocode audit on native 10 km grid
Ensure the old Stage62b + Stage72 QC passed and the 10 km Parquet exists (READ-ONLY). Then run:

    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding labels --raw E:\GEE_flooding\data\raw\groundsource_2026.parquet --grid E:\Global_flooding\grid10\universe\grid10_urban_2020.parquet --grid-qc E:\Global_flooding\grid10\universe\62b_grid10_qc.json

Results: outputs/labels (primary news geocodes and full rejection audit) and reports/qc/labels_qc.json, all under E:\GEE_flooding. HIGH geocode quality is a *geometry-specificity proxy* only.

## Later supervised proof of concept (requires independently prepared event-exposure weather data)
The external weather parquet MUST contain all storm-exposed grid-day rows, not just news positives, with columns:
grid_id,date,storm_id,city_id,rain_24h_mm,rain_3h_mm,api_7d_mm.

The static parquet MUST have one row per grid_id with:
grid_id,hand_m,slope_deg,urban_fraction_2020,vegetation_fraction.

    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding panel --weather E:\GEE_flooding\data\derived\storm_exposure_weather.parquet --static E:\GEE_flooding\data\derived\static_grid_factors.parquet --labels E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet
    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding baseline --panel E:\GEE_flooding\outputs\panels\storm_exposure_with_news_labels.parquet

Do NOT execute these steps until the independent storm catalogue and both input parquets genuinely exist. The M0–M2 ablation uses a joint *held-out-city and held-out-storm* test; scores are for a **news-reported vs unlabeled** proxy, not measured flood probability. Validating true flood susceptibility requires independent flood/non-flood observations.

## Reproducibility and scope
- Never store large parquet, GeoTIFF, data secrets or trained models on GitHub.
- Dataset/source copyright remains with publishers; Groundsource CC BY 4.0.
- Do not silently substitute SMOD urban fraction for GHS-BUILT-S built fraction.
- This first release is a reproducible Stage 0–2 research scaffold, not a completed worldwide ML risk map or a live GEE export pipeline.
- Details: docs/RESEARCH_PROTOCOL.md and config/project.json.
