# GEE_flooding Figure 1 v3 — P0 runbook and public evidence

**SCOPE:** This is the standalone Communications Earth & Environment manuscript. NOT the Nature Cities paper. Figure 2 code is owned by another conversation. Web ChatGPT edits and merges GitHub. Local Codex executes commands, inspects real E:/D: files and reports back. All NEW output under E:\GEE_flooding. Old paths only read.

## Existing local data: DO NOT RE-DOWNLOAD

- E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet
- E:\GEE_flooding\reports\qc\labels_qc.json
- E:\GEE_flooding\data\reference\grid10_urban_2020.parquet
- E:\GEE_flooding\outputs\fig1_v2\fig1_ucdb_city_sample_audit.csv
- E:\GEE_flooding\outputs\fig1_v2\fig1_grid_dominant_ucdb.parquet
- E:\Global_flooding\grid10\reference_external\GFID\AggregatedFloodData.xlsx
- E:\Global_flooding\grid10\reference_external\GFID\Potential_Duplicate_Events.csv
- E:\Global_flooding\grid10\fig1_public\natural_earth\ne_110m_admin_0_countries.shp
- E:\数据集 local CN-Floods, Henan, London surface water, China county urban flooding datasets and social flood sources. Existing path is not proof of true observed inundation.
- E:\Global_flooding\grid10\gfd_physical_v3: eight READY Earth Engine tasks are NOT real results until success and actual downloaded output is verified.

The v2 facts: 2,646,302 raw Groundsource news rows; 2,202,651 mapped; 1,788,759 HIGH; 1,056,639 unique HIGH GF10 grid-days; 166,414 study grids; 11,422 UCDB official cities; 7,239 eligible according to **all-years** selection. Source polygons are geocoded place extents, NOT flooded footprints.

## P0 analysis implemented

1. GFID reads every row of the USGS Aggregated workbook. Classifies source family (DFO/DesInventar/EM-DAT/HANZE), Date fallback, missing/partial start, missing end (flagged one-day candidate), coordinates, date-window and exclusive exclusion reason. Preserves all 136,642 rows. Accepted GFID coordinates remain approximate index points, never observed inundation. Compares 25/75/150km and 0/3/7 days, including a +183-day falsification time-shift. Some GFID sources share underlying events; USGS Potential_Duplicate_Events.csv is potential overlap, not definitive deduplication.
2. UCDB crosswalk audits 702,479 HIGH reported UUIDs without official city ownership. Broad GF10 urban domain and UCDB urban-centre polygons differ; do not call unmatched geocodes invalid. Official city continent Unknown can only be repaired by actual Natural Earth polygon intersection, without guessed nearest-country assignment.
3. City eligibility is recomputed using only 2021–2023 development labels (default >=5 HIGH reports in >=2 development years). A frozen hash of city ID and climate/continent stratum allocates city candidates; 2024–2025 is NOT allowed to affect city selection. The new eligible city count is NOT supposed to equal the v2 all-years 7,239.
4. A reproducible ~600-row human annotation queue covers geocode classes and eras, with selection probabilities. Reviewers must independently verify location/time, actual flooding and pluvial mechanism, document evidence and reviewer IDs; use stratified uncertainty rather than overall anecdotal rates.
5. A source inventory scans already-held physical reference files, *without reading entire massive raster arrays*. Optional strict physical CSV accepts only actual independently reviewed positive observations from in-situ/optical/SAR and metadata. Not every river flood pixel is pluvial, and satellite non-detection is NOT a flood-free negative.

## Windows: first sync main code (Codex should only update new source code; preserve local data), then

    Set-Location E:\GEE_flooding
    $PY = "E:\GEE_flooding\.venv\Scripts\python.exe"
    & $PY -m pip install -e ".[test]"
    & $PY -m pytest -q

First run an explicitly incomplete smoke check (first 1,000 HIGH grid-days in GFID candidate comparison only):

    .\scripts\run_fig1_v3.ps1 -Root E:\GEE_flooding -V2Tag fig1_v2 -Tag fig1_v3_smoke -Fast

Then full run (do not overwrite previous version):

    .\scripts\run_fig1_v3.ps1 -Root E:\GEE_flooding -V2Tag fig1_v2 -Tag fig1_v3_full

Expected output under E:\GEE_flooding\outputs\fig1_v3_full:

- Figure1_GEE_v3.png / pdf / svg (six panels)
- fig1_v3_qc.json
- gfid_row_level_quality.parquet; gfid_reason_by_family.csv; gfid_candidate_sensitivity.csv
- ucdb_city_development_holdout.csv; ucdb_missing_assignment_by_period_and_urban_share.csv; ucdb_eligibility_by_continent_koppen.csv
- independent_groundsource_annotation_queue.csv
- local_physical_source_inventory.csv
- physical_evidence_input_template.csv

Smoke outputs are marked sensitivity_is_full_data FALSE and MUST NOT be cited.

## Physical CSV input contract

After genuine independent source and location/date review, fill template with exact columns:

    source_record_id,source_family,observation_date,longitude,latitude,
    observation_type,pluvial_class,valid_spatiotemporal_coverage,
    independent_source_confirmed,reviewer_id,evidence_uri,
    location_precision_m,flood_observed

Use observation_type FIELD_OBSERVATION / IN_SITU_SENSOR / SAR_VERIFIED / OPTICAL_VERIFIED / OFFICIAL_EVENT_LOCATION.
Only CONFIRMED_PLUVIAL with documented independent lineage and coverage is counted as a confirmed-pluvial positive. YES/NO are strict; any flood_observed=NO is rejected by this positive-only protocol because monitored negatives need a separate, more rigorous coverage process.

    .\scripts\run_fig1_v3.ps1 -Root E:\GEE_flooding -Tag fig1_v3_physreview -PhysicalTable E:\GEE_flooding\data\validation\independent_physical_points.csv

This is CASE-STUDY positive support, NOT representative global precision/recall or proof of geocoder point accuracy.

Manual label review uses independent_groundsource_annotation_queue.csv. Populate reviewer_id, evidence_source_uri, location_verified, date_verified, flood_occurrence_verified, pluvial_mechanism_verified and independent_of_groundsource with YES, NO or blank when unresolved. Then run a new tag with -ReviewerTable to compute reviewed sample estimates. Auditing selection, inter-rater consistency and confidence intervals is still necessary; 600 is a planning target, not a journal-required sample size.

## Official source links and downloading policy

**No global dataset download is required now.** First inspect existing local files and distinguish true physical observations from model or news archives.

- USGS GFID official: https://doi.org/10.5066/P135ARGI — already local; do not download.
- NASA Global Flood Database: https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1 — existing GEE image collection; 913 DFO-origin MODIS events at 250 m, clear-view and permanent-water QA; no global MODIS download.
- Copernicus Emergency Management GFM SAR: https://emergency.copernicus.eu/data/ — optional targeted event/city Sentinel-1 observations; free to view/download, not automatically local pluvial ground truth.
- CrowdFlood Weibo 40k+ China inundation locations, 2021–2025: https://zenodo.org/records/19921295 — OPTIONAL only if existing local social data do not already contain it. Social media ≠ independent physical measurement.
- Chinese urban flood crowdsourcing inventory NUFI: https://zenodo.org/records/18017214 — OPTIONAL only after local county data comparison. District/county observations not precise 10km flood footprint.
- China Flood Disaster Impact Database 1994–2023: https://zenodo.org/records/22918521 — OPTIONAL for separate catalogue sensitivity, not measured local inundation.

Example lookup for an optional Zenodo record (not a download):

    & $PY -c "import requests; r=requests.get('https://zenodo.org/api/records/19921295',timeout=30); r.raise_for_status(); print([(f['key'],f.get('size')) for f in r.json()['files']])"

If and only if needed, use the exact official Zenodo record file link, save under E:\GEE_flooding\data\external\<dataset>, and verify the advertised MD5. Do NOT re-download raw Groundsource, GHSL, IMERG, GFID, WorldCover, GFD imagery, DEM or UCDB.

## Scientific acceptance / remaining P0

A. GFID: All source rows accounted for with exclusive reasons; DesInventar presence and date precision; source-duplicate caveats; sensitivity window plus shifted-time control. Never call this independent physical validation.
B. City selection: Preserve and explain unmatched HIGH UUIDs, unknown continent, geographical reporting bias. Use 2021–2023 only for development eligibility.
C. Genuine external physical evidence: at least several heterogeneous climate/city examples with verifiable timestamps, actual water observations, source independence and flood mechanism; avoid sampling only easy positives. Absence of flood observation is not observed no-flood.
D. Annotate original news location with review protocols and stratified uncertainty / inter-rater checks. The real independent physical review cannot be fabricated by code and must be completed by Codex/local scientists.
E. The fig1_v3_qc status remains PREPUBLICATION_P0_PENDING until these checks and actual regional-source review are passed. Section 3.2 belongs to another conversation and is not changed here.
