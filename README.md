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
    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding inventory
    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding summarize-labels

**Existing data reuse:** do NOT re-run `download`, `bootstrap-grid`, or `labels` if their current outputs and QC already passed. The download command is a recovery-only option when the source is genuinely absent; the user already has its verified MD5. The no-download inventory checks historic paths read-only, without attempting a network call.

## First production commands: new-project grid and label QC
The two previously downloaded SMOD TIFFs are READ-ONLY. Run the built-in freezer to generate a fresh GF10 reference entirely under E:\GEE_flooding:

    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding bootstrap-grid --west E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s00.tif --east E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s01.tif

It writes the grid and QC only under E:\GEE_flooding\data\reference. Then assign original source events:

    .\.venv\Scripts\python.exe -m gee_flooding --root E:\GEE_flooding labels --raw E:\GEE_flooding\data\raw\groundsource_2026.parquet --grid E:\GEE_flooding\data\reference\grid10_urban_2020.parquet --grid-qc E:\GEE_flooding\data\reference\grid10_qc.json

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
- This first release is a reproducible grid+label Stage 0–2 research scaffold, not a completed worldwide ML risk map or a live GEE export pipeline.
- Details: docs/RESEARCH_PROTOCOL.md and config/project.json.

## GEE manuscript Figure 1 — NEW (no downloads, independent project)

Figure1 has five panels: news coverage, geocode audit, annual archive availability, GFID catalogue candidate concordance (not satellite validation), and official UCDB city study eligibility. It is NOT the Nature Cities Figure1.

Full data matrix, paper Data availability citations and caveats: [Figure1 data availability](docs/FIGURE1_DATA_AVAILABILITY.md).

Read-only local execution (existing environment and locally held data):

    Set-Location E:\GEE_flooding
    .\scripts\run_fig1.ps1 -Root E:\GEE_flooding -Tag fig1_v1

No new Groundsource/GF10/GFID download and no GEE submission. Results: E:\GEE_flooding\outputs\fig1_v1, including PNG/PDF and quality provenance JSON. If the existing Natural Earth or Koppen file path is unavailable use -SkipWorld or -SkipKoppen for an explicitly incomplete draft, or correct the local path before calling the CLI.

The new Figure1 remains DRAFT_NEEDS_INDEPENDENT_PHYSICAL_VALIDATION until previously downloaded CN-Floods/Henan/London or actual successful GFD/SAR exports undergo independent validation. Eight READY Earth Engine tasks are not completed physical evidence.
