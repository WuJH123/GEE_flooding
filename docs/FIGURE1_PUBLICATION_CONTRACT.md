# Figure 1 publication contract — GEE_flooding (independent CEE study)

DO NOT USE for Nature Cities project or Figure 2. Web GPT edits GitHub; local Codex runs E-drive data. Existing original sources are read-only. New results ONLY under E:\\GEE_flooding.

## Five required panels

1a — Frozen EPSG:6933 10km 2020 urban core (166414 original GF10 cells) and audited one-cell 10km peripheral raster frame. Show geocoded news density; grey/no-report areas do NOT mean no flood.

1b — Distinguish raw UUID records, mapped records, A/B/C quality tiers, unique grid-days and contiguous-grid candidate clusters. These are NOT proven independent physical flood events or independent meteorological storms. Storm counts require an independently meteorology-derived storm manifest.

1c — Official UCDB city denominators and A/B/C recording quality by country/continent/Koppen, and annual archive availability. Publication city size must derive from an identified actual UCDB 2020 total-population field; do not invent variable names. Old unknown continent remains Unknown.

1d — Source-family catalogue concordance (USGS GFID/DFO/EM-DAT/DesInventar/HANZE) clearly separate from actual CEMS/GFD/field confirmed inundation. 913 GFD MODIS events derive event selection from DFO; optical water detection is a measurement but may not diagnose pluvial mechanism. CEMS extent also needs valid coverage and source lineage. If no reviewed physical observations, panel says PENDING.

1e — UCDB official cities in news TRAIN_CANDIDATE, HELDOUT_CITY_CANDIDATE, INSUFFICIENT_NEWS_EVIDENCE. Qualifiers use only 2021–2023 development information, not 2024–2025 outcomes. Insufficient evidence is NOT low pluvial hazard or an evaluated forecast.

## Prespecified A/B/C source-geocoder/time PROXY (not physically validated accuracy)

A: original geocoder area <=25 km2, dominant 10km grid overlap >=0.8, <=4 mapped urban cells and start/end interval <=1 day.
B: area <=100 km2, overlap >=0.5, <=16 cells, interval <=3 days, excluding A.
C: all remaining mapped UUIDs including missing/uncertain metadata. Original HIGH/MEDIUM/LOW is kept separately. Original geometry area represents geocoding uncertainty, NOT observed flooded area; start/end span is a coarse timing proxy, NOT independently measured date precision. No empirical accuracy claim until independent reviewer validation, confidence intervals and sensitivity to thresholds.

## Already downloaded (NO bulk redownload)

- E:\\GEE_flooding\\data\\raw\\groundsource_2026.parquet (2,646,302 rows in previous audit).
- E:\\GEE_flooding\\data\\reference\\grid10_urban_2020.parquet and two read-only SMOD tif stripes in E:\\Global_flooding\\grid10\\gee_tifs.
- E:\\GEE_flooding\\outputs\\labels\\groundsource_gf10_primary.parquet; v2 dominant UCDB crosswalk; v3 full_r2 UCDB city and GFID source QC products.
- Local GHS-UCDB GPKG, GFID workbook and potential duplicate CSV, local Koppen, China CN-Floods, Henan raster, London model hazard maps.
- Existing GFD READY tasks are NOT completed satellite observations. Never treat a hazard model as measured flood or GDID/DFO duplicate event as new independent physical measurement.

## Official optional observation sources (only selected event/cell downloads if required)

- Groundsource original: https://doi.org/10.5281/zenodo.18647054 (already local)
- USGS GFID: https://doi.org/10.5066/P135ARGI (already local; representative GFID coordinates NOT inundation)
- CEMS event mapping and Copernicus GFM: https://emergency.copernicus.eu/data/ and https://mapping.emergency.copernicus.eu/ (download dated flood extent AND sensor/valid-observation metadata per selected activation)
- GFD MODIS built into GEE: https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1 ; Earth Engine Collection GLOBAL_FLOOD_DB/MODIS_EVENTS/V1 (flooded, clear_views, clear_perc, jrc_perm_water, metadata; 913 DFO-selected mapped floods; cloud/non-detection NOT ground-truth absence).
- GHSL GHS-UCDB 2025 reference: https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php (already local, 11422 urban centers).

## Run from PowerShell after local Codex synchronizes merged GitHub main

Set-Location E:\\GEE_flooding
$PY = 'E:\\GEE_flooding\\.venv\\Scripts\\python.exe'
& $PY -m pip install -e '.[test]'
& $PY -m pytest -q

Inspect UCDB population schema first (NO download):

& $PY -m gee_flooding --root E:\\GEE_flooding fig1-ucdb-population --ucdb 'E:\\数据集\\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\\GHS_UCDB_GLOBE_R2024A.gpkg' --tag fig1_ucdb_schema_r1

Read the JSON under outputs/fig1_ucdb_schema_r1/ucdb_population and select exact verified 2020 TOTAL population field, NOT a share/density/other epoch; rerun with a NEW tag and --population-field FIELDNAME to make a city_id,population_2020 CSV.

Produce Five-panel Figure 1 using existing GF10/Groundsource/UCDB/GFID, NO downloads:

.\\scripts\\run_fig1_publication.ps1 -Root E:\\GEE_flooding -Tag fig1_publication_v1 -V2Tag fig1_v2 -V3Tag fig1_v3_full_r2

Optional: -CityPopulation E:\\GEE_flooding\\outputs\\fig1_ucdb_pop_r2\\ucdb_population\\ucdb_population_2020.csv ; -PhysicalReviewed E:\\GEE_flooding\\data\\validation\\independent_physical_points.csv ; -IndependentStormManifest E:\\GEE_flooding\\data\\derived\\independent_storms.csv . External physical inputs MUST be independent reviewed positive observations under the existing v3 strict schema; storm manifest must come from meteorology rather than Groundsource.

Outputs under outputs/fig1_publication_v1/: grid/gf10_core_periphery_2020.parquet and spatial_frame_qc.json; labels/raw_uuid_tiers.parquet, grid_day_observations.parquet, candidate_grid_episodes.parquet, label_tier_qc.json; paper/Figure1_publication_draft.pdf/.svg/.png, figure1_publication_gate.json, annual_ABC_news_coverage.csv, official_city_coverage_and_split.csv, coverage_by_country.csv, coverage_by_continent.csv, coverage_by_koppen_broad.csv, coverage_by_population_class.csv, country_climate_city_size_coverage.csv.

## Real publication P0 still needed

- Review stratified original news cases with independent original articles/verified sources, double reviewer subset, tier-specific location/date error, sample inclusion probabilities and uncertainty intervals; 600-row v3 review queue currently unreviewed.
- CEMS/GFD/local satellite or ground-positive cases with observed flooded geometry, precise date, valid observation masks, independent sensor data, reviewer, water-body exclusions and pluvial-mechanism judgement. Do not use GFD/DFO duplicated catalogues as independent event counts.
- External climate/country/population-size representation estimates with official UCDB denominator and reporting coverage; document unresolved countries and heterogeneity without claiming all low-income regions underreport.
- For actual independent storm counts, add an external IMERG/ERA5 meteorological tracker. Contiguous news-grid episode clusters are not substitute.
- Training/validation source lineage for Section 3.2 is independent responsibility; release figure statuses must not falsely mark unverified risk as accurate prediction.

A figure rendering successfully means CODE COMPLETE, not SCIENTIFIC VALIDATION COMPLETE. Keep DRAFT status whenever physical, sample review, meteorological event identification, population or lineage evidence is missing.
