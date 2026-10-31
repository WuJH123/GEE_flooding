# Figure 2 Codex pilot -> GF10 backfill (2026-10-31)

This runbook is grounded in uploaded fig2_local_first_qc.json, fig2_core_indicator_gate.csv, fig2_indicator_coverage.csv, fig2_gee_missing_indicator_plan.csv, and FIG2_LOCAL_FIRST_PILOT_20261031.md. This repository cannot see the user's Windows E: drive. No Earth Engine task has been submitted here.

## Verified facts and scientific limits

- Targeted path index: 3,408 paths; 103 candidate matches in 14 families, NOT a 240,000-file exhaustiveness audit.
- Frozen pilot: 40 official UCDB cities, 182 GF10 10km cells (32 development and 8 heldout cities).
- Local source: GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0.tif, native 100m, ESRI:54009 equal area, 1 band uint16 and 65535 nodata. Source stores built m² per native pixel. 20/182 accepted, coverage 98.78-100%; built area in km² equals 100 times GF10 built fraction. These two outputs are arithmetic transforms of ONE source and do not constitute independent agreement.
- Urban fraction frozen from original GF10: 182/182. Eleven of 12 core/exposure indicators have missing data; HAND, slope, upstream area, vegetation, population, NRES, built growth/neighbor/fragmentation each 0/182.
- 99 GISD30 dynamic candidate TIFFs have EPSG:4326 degree cells. Their pixel classes cannot be averaged as impervious fraction: original dynamic codes 0 pervious; 1 pre-1985 impervious; 2-8 later expansion epochs. Recode to binary for a target year only after confirming product metadata. They are P1 sensitivity, NOT GHSL 2020 substitute.
- No GEE tasks submitted, no independent physical flood positive and monitored dry reference, and no 2021-25 IMERG panel ready.

## 0. Correct Git setup: separate immutable data and code folders

Codex says the data folder E:\GEE_flooding has NO .git, so git pull there is invalid. Do NOT reinitialize, delete or overwrite it. Use a clean separate source clone and --root pointing to the old data directory.

PowerShell:

    $ROOT='E:\GEE_flooding'
    $SRC='E:\GEE_flooding_code'
    if (-not (Test-Path "$SRC\.git")) {
      git clone https://github.com/WuJH123/GEE_flooding.git $SRC
    } else {
      Set-Location $SRC
      git pull --ff-only origin main
    }
    Set-Location $SRC
    git log -1 --oneline
    $PY="$ROOT\.venv\Scripts\python.exe"
    if (-not (Test-Path $PY)) { py -3.11 -m venv "$ROOT\.venv" }
    & $PY -m pip install -e "$($SRC)[test,local]"
    & $PY -m pytest -q

## 1. Finish the KNOWN 2020 GHSL globally available source on all 182 cells, without re-download

The supplied audit locates the actual tif at:

    E:\数据集\全球人类居住层GHS built-up surface (R2023)\GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0\GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0.tif

Check the path and current frozen GF10 sample tag in your workspace before running. If it is absent, find the REAL 182-row file under data/reference/fig2_subset_*; never make up a grid file.

    $GRID="$ROOT\data\reference\fig2_subset_local_v1\fig2_GF10_selected_grid.parquet"
    $GHS='E:\数据集\全球人类居住层GHS built-up surface (R2023)\GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0\GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0.tif'
    if (-not (Test-Path $GRID) -or -not (Test-Path $GHS)) { throw 'Check GF10 pilot or original GHSL tif path' }
    New-Item -ItemType Directory -Force "$ROOT\data\reference\fig2_manual" | Out-Null
    $vars=@(
      @{name='built_fraction_2020'; dataset='GHSL_BUILT_S_R2023A'; epoch='2020'; kind='cell_sum'; native_units='m2_per_native_pixel'; band=1;paths=@($GHS)},
      @{name='built_area_km2_2020'; dataset='GHSL_BUILT_S_R2023A'; epoch='2020'; kind='cell_sum'; native_units='m2_per_native_pixel'; band=1;paths=@($GHS)}
    )
    @{variables=$vars} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 "$ROOT\data\reference\fig2_manual\ghsl2020.json"
    & $PY -m gee_flooding.fig2_local_exact --root $ROOT --grid $GRID --manifest "$ROOT\data\reference\fig2_manual\ghsl2020.json" --start-row 0 --count 182 --min-coverage 0.95 --backend shapely --tag fig2_local_ghsl182_v2

The Shapely backend is now explicitly implemented, source-audited and limited to verified metric equal-area raster CRS ESRI:54009/EPSG:6933. No silent fallback. The C++ exactextract backend remains preferred if locally available. A 20/182 historical extraction must not overwrite this new version.

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local "$ROOT\data\derived\fig2_local_ghsl182_v2\fig2_local_GF10_indicators.parquet" --tag fig2_integrated_ghsl182_v2
    $MERGED="$ROOT\data\derived\fig2_integrated_ghsl182_v2\fig2_GF10_resilience_indicators.parquet"

Check the local extraction QC, coverage and how many of 182 GF10 remain NaN. Compare native-source JRC polygon totals independently before claiming area conservation.

## 2. Automatically plan only missing GF10 rows and necessary predictor bands by source family

    & $PY -m gee_flooding.fig2_backfill_plan --root $ROOT --grid $GRID --indicators $MERGED --scope core --max-cells 20 --tag fig2_gee_backfill182_core_v2
    $TASKS="$ROOT\data\reference\fig2_gee_backfill182_core_v2"
    Import-Csv "$TASKS\fig2_gee_backfill_tasks.csv" | Group-Object source_family | Select-Object Name,Count
    Get-Content "$TASKS\fig2_gee_backfill_plan_qc.json"
    & "$TASKS\fig2_gee_backfill_dry_runs.ps1"

This outputs grouped MERIT (HAND/slope/upa), WorldCover vegetation, built GHSL morphology and GHSL population/exposure. Only missing combinations of cells and columns are selected. Source IDs, bounds and the EPSG:6933 frozen grid are carried through unchanged. All tasks are DRY_RUN and NOT submitted. Use --scope extended on a NEW tag only after core source tests.

## 3. Submit ONE task; inspect actual EE bands and CSV before any larger campaign

    $EE="$ROOT\.venv\Scripts\earthengine.exe"
    & $EE authenticate
    & $EE set_project YOUR_EE_CLOUD_PROJECT
    $PROJECT="YOUR_EE_CLOUD_PROJECT"
    $row=Import-Csv "$TASKS\fig2_gee_backfill_tasks.csv" | Select-Object -First 1
    $FILE=Join-Path $TASKS $row.grid_file
    & $PY -m gee_flooding.fig2_gee --grid $FILE --mode $row.mode --bands $row.bands --start-row 0 --count ([int]$row.n_grid) --project $PROJECT --submit

Task SUBMITTED/READY/RUNNING != verified data. Wait for COMPLETED at https://code.earthengine.google.com/tasks and DOWNLOAD corresponding Drive CSV. Manually review row counts, missing values, original units and native GHSL area/pop conservation. Do not loop all tasks before a successful real server-side smoke test. Downloads go to data/gee_exports/fig2_static or data/gee_exports/fig2_exposure.

    & $PY -m gee_flooding.fig2_indicators --root $ROOT --grid $GRID --local "$ROOT\data\derived\fig2_local_ghsl182_v2\fig2_local_GF10_indicators.parquet" --gee-static "$ROOT\data\gee_exports\fig2_static" --gee-exposure "$ROOT\data\gee_exports\fig2_exposure" --tag fig2_integrated_after_GEE_v3

Omit a --gee-* argument if no completed matching CSV exists. Review source_conflicts.csv and core_indicator_gate.csv. Never interpret absent/invalid as zero.

## 4. Secondary data and final publication gates

First search the historical real E:\数据集 and E:\Global_flooding folders for GHSL 2000/POP, MERIT, WorldCover and IBTrACS before deciding local is absent; the submitted 3408 path index was not exhaustive. Current task does NOT download anything. GISD30 1985-2020 needs explicit class recoding and audited equal-area processing (EPSG:4326 source rejected in the Shapely backend); its proper scientific use is an imperviousness robustness check. NOAA IBTrACS is only for tropical-cyclone matching. No third-party dataset under 10GB needs downloading yet for core GF10 if official Earth Engine layers can supply it.

The 182-cell static pilot is NOT a global representative population nor complete Figure2. Next P0s: complete original half-hour IMERG V07 2021–2025 and preceding seven days (48/336 slots), ERA5-Land antecedent moisture, meteorological storm grouping independent of news, same-row M0–M5 ablation and heldout cities/countries/years/storms; independent actual pluvial inundation positives AND independently monitored dry observations. Otherwise title the result as reported-flood response, not true flood probability.

Official source documentation:
https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S
https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_POP
https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
https://essd.copernicus.org/articles/14/1831/2022/
