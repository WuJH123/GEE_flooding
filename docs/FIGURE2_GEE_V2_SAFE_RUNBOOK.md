# Figure 2 GF10 GEE v2: safe export and urban resilience indicator handbook

**Status:** code and synthetic CI only. This repository cannot access the user's E: drive or submit
Earth Engine jobs without their locally authenticated GEE environment. Actual CSV downloads and
real figure output remain P0 prerequisites; do not claim completion from a DRY_RUN/SUBMITTED result.

## Why GF10GFD and GHS10 jobs failed

- GFD: `Projection: The CRS of a map projection could not be parsed`. Known
  EPSG:6933 Earth Engine raster reprojection compatibility problem
  (https://github.com/google/earthengine-community/issues/971).
  The *original* failed task script is not in this repository, so exact triggering
  statement cannot be proven from its task name. The new GEE code never asks EE
  to parse EPSG:6933; the client uses pyproj to build densified EPSG:4326
  polygons from the authoritative 10km grid and carries over the original grid_id.
  Cell IDs and the EPSG:6933 equal-area cell geometry remain unchanged in the research dataset.
  Antimeridian cells fail closed rather than becoming spanning polygons.
- GHSL: `Reprojection output too large (26574x25289 pixels)`, over 670 million
  raster pixels. Do NOT increase maxPixels or use `Export.image.toDrive` with
  giant global region. New pipeline exports bounded `Export.table.toDrive`
  per selected GF10 cell, grouped by weather, terrain/surface, and population/
  built-area context. No export requests a large raster at 10/30/100m global extent.
- Earth Engine official reference for table export:
  https://developers.google.com/earth-engine/apidocs/export-table-todrive
- The old failed tasks cannot be retroactively edited. Do not repeat them.
  Create **new tasks** with versioned `f2_*` descriptions.

## Scientific framework: hazard × exposure × sensitivity × adaptation proxy

**Every output is indexed by the same frozen 10km GF10 grid_id.** Native data
remain 10m/90m/100m/~11km; we aggregate or sample to GF10, not pretend to
increase native physical resolution. The dictionary is code-generated under
`reports/fig2_inputs_v2`, including units, epoch, aggregation, primary role
and origin.

| Pillar | Core indicators | Interpretation |
|---|---|---|
| Meteorological hazard | IMERG 3h rolling maximum, 24h total, antecedent 7d, sample counts; ERA5-Land antecedent surface/7–28cm soil moisture and air temperature | Storm intensity, wetness, data validity |
| Exposure | Frozen 2020 urban fraction; GHSL BUILT-S total/nonresidential fraction and area; GHS-POP 2020 population; urban-growth 2000–2020 | Potentially exposed urban fabric and inhabitants |
| Hydrological sensitivity / vulnerability | MERIT HAND, elevation, slope, upstream area, permanent river water fraction, bare and water shares, built fraction fragmentation | Physical susceptibility proxies, not sewer hydraulic capacity |
| Green-blue adaptation proxies | WorldCover vegetation/tree/grass/cropland/wetland shares and local green structure | Potential natural retention, NOT observed adaptation or investment |
| Reporting/observation selection | Historical country/year internet usage, nightlights, accessibility, geocode quality, GFD clear_views and satellite observability | Must enter independently audited selection or coverage analyses, never labelled as genuine no-flood |
| Optional local indicators (NOT automatically loaded) | WorldPop, GHSL BUILT-V, GAIA/GISD30 imperviousness, GRIP roads, transport accessibility, GDP, NDVI | Need date, license, cell intersection and source-unit audit before join |

Use GHSL population and built-surface totals for exposure conclusions **only
after conservation checks** against reference pixels: summing remapped 100m
pixels at nominal 100m EPSG:4326 may introduce area/pixel-grid mismatch.
Don't treat approximate exported totals as an official GHSL tabulation without
that check.

Resilience is a conceptual grouping. Neither an observed city sewer network
nor emergency response capability is provided by these open layers. Vegetation
is a *potential protective proxy*, not measured adaptive capacity; ecological
correlations are not causal.

### Open dataset provenance

- IMERG V07: `NASA/GPM_L3/IMERG_V07` 0.1-degree half-hourly rate (mm/hour,
  integrate per 0.5h): https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- ERA5-Land: `ECMWF/ERA5_LAND/HOURLY`, soil moisture volumetric fraction and
  air temperature K (subtract 273.15): https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY
- MERIT Hydro: `MERIT/Hydro/v1_0_1`, 90m hnd/elv/upa/wat; upstream km²:
  https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
- WorldCover: `ESA/WorldCover/v200`, 2021 10m Map 11 classes:
  https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- GHSL BUILT-S: `JRC/GHSL/P2023A/GHS_BUILT_S/2000` and `/2020`,
  surface in m² per 100m pixel: https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S
- GHSL POP: `JRC/GHSL/P2023A/GHS_POP/2020`, population count:
  https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_POP
- GFD: `GLOBAL_FLOOD_DB/MODIS_EVENTS/V1`, events 2000–2018:
  https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1

## Windows PowerShell — exact next steps

### A. Sync/verify and inventory, NO downloads or GEE submission

```powershell
Set-Location E:\GEE_flooding
git status --short
git fetch origin
git pull --ff-only origin main
$PY="E:\GEE_flooding\.venv\Scripts\python.exe"
& $PY -m pip install -e ".[test]"
& $PY -m pip install earthengine-api
& $PY -m pytest -q
& $PY -m gee_flooding.fig2_resilience --root E:\GEE_flooding --tag fig2_inputs_v2_20261031
.\scripts\run_fig2.ps1 -Phase preflight
```

Local original Groundsource and GF10 should be used from `E:\GEE_flooding`.
Potential additional archives in `E:\Global_flooding` and `E:\数据集` are
**read-only references**, not aligned GF10 feature tables. Inventory verifies
existence, not quality. DO NOT repeat original Groundsource downloads,
Figure1 grid freezing or label assignments.

### B. Build a geographic not news-selected subset

```powershell
$ROOT="E:\GEE_flooding"
$GRID="$ROOT\data\reference\grid10_urban_2020.parquet"
$F1="$ROOT\outputs\fig1_v2"
& $PY -m gee_flooding.fig2_sampling --root $ROOT `
  --grid $GRID `
  --crosswalk "$F1\fig1_grid_dominant_ucdb.parquet" `
  --cities "$F1\fig1_ucdb_city_sample_audit.csv" `
  --max-cities 40 --cells-per-city 12 `
  --seed 42 --tag fig2_subset_v2
$STUDYGRID="$ROOT\data\reference\fig2_subset_v2\fig2_GF10_selected_grid.parquet"
```

This makes an exploratory approximately 480-cell subset stratified over
official UCDB continent and Köppen categories (actual count depends on coverage).
Selection does **not use news outcomes**. Check audit and improve representativeness
before publication. A few geographic cells cannot prove worldwide uniform accuracy.

### C. Earth Engine authentication (only if needed)

```powershell
$EE="E:\GEE_flooding\.venv\Scripts\earthengine.exe"
& $EE authenticate
& $EE set_project YOUR_EARTH_ENGINE_CLOUD_PROJECT
```

Earth Engine service needs its own account/project; Google Drive output is
uploaded there by an authorized local process.

### D. Small, deliberate dry-run (no remote tasks)

```powershell
& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode static --start-row 0 --count 20
& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode exposure --start-row 0 --count 20
& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode weather --date 2023-08-01 --start-row 0 --count 20

# Optional historic GFD (DO NOT confuse the failed DF004695 job name
# with the verified Dartmouth id until cross-checked in the GFD metadata):
& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode gfd --gfd-id 3977 --start-row 0 --count 20
```

GFD 3977 is an official catalogue demonstration ID, not a 2021–2025
physical validation. GFD-only `flood_fraction_observable` counts water among
satellite-observable nonpermanent land. No coverage/visibility does **not**
mean a dry location.

### E. Submit ONE new verified task of each type, NOT original failed scripts

```powershell
& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode static `
  --start-row 0 --count 20 --submit --project YOUR_EARTH_ENGINE_CLOUD_PROJECT

& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode exposure `
  --start-row 0 --count 20 --submit --project YOUR_EARTH_ENGINE_CLOUD_PROJECT

& $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode weather `
  --date 2023-08-01 --start-row 0 --count 20 `
  --submit --project YOUR_EARTH_ENGINE_CLOUD_PROJECT

# Historical GFD is independent supplementary, only submit after metadata audit:
# & $PY -m gee_flooding.fig2_gee --grid $STUDYGRID --mode gfd `
#   --gfd-id 3977 --start-row 0 --count 20 --submit --project YOUR_EARTH_ENGINE_CLOUD_PROJECT
```

**Do not bulk loop these commands**. Confirm each task COMPLETED on the
Earth Engine Tasks page, then download its matching CSV from the GEE_flooding_Figure2
Drive folder. Resume in small batches with a documented complete task list.
No Image.toDrive, EPSG:6933 GEE raster reprojection, or giant `scale:10`
global request is allowed.

Put completed files in:

```powershell
New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_static"
New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_exposure"
New-Item -ItemType Directory -Force "$ROOT\data\gee_exports\fig2_weather"
```

### F. Real model preparation, only AFTER 100% of declared space × date CSV exports pass QC

Before running, the selected slice must contain every cell for **each**
declared UTC date, including the previous 7-day IMERG history and valid
ERA5-Land values, and static/exposure rows for every cell. An isolated
single-day/20-cell smoke sample is not a usable city/storm transfer set.

```powershell
.\scripts\run_fig2.ps1 -Phase prepare -Root $ROOT `
  -Fig1Tag fig1_v2 -GridPath $STUDYGRID `
  -StartRow 0 -Count 20 -Start "2023-08-01" -End "2023-08-31" `
  -ExposureDir "$ROOT\data\gee_exports\fig2_exposure"

.\scripts\run_fig2.ps1 -Phase train -Root $ROOT `
  -Fig1Tag fig1_v2 -GridPath $STUDYGRID -Tag fig2_v2
```

The prepare script *fails closed* for incomplete rain bins, GHSL or static
coverage, duplicate IDs and null features. Outputs under the new project:
- `data/derived/storm_exposure_weather.parquet` (IMERG + ERA5 if downloaded);
- `data/derived/static_grid_factors.parquet` and `fig2_extended_grid_factors.parquet`;
- `data/derived/fig2_resilience_all_static_GF10.parquet`;
- `data/derived/fig2_ghsl_population_context_GF10.parquet` (if provided);
- `data/derived/fig2_weather_provenance.json`;
- `outputs/fig2_v2/Figure2_news_proxy.png/.pdf` and metrics (ONLY with
  statistically valid jointly heldout city/storm test folds).

Outputs are non-overwriting/versioned. The manuscript scope still needs
2021–2023 development and 2024–2025 genuinely prospective evaluation,
reporting-selection sensitivity, and valid independent pluvial positives and
observed dry records; no GFD catalogue/task ID is enough.

## P0 before claiming Figure2 completed

1. Test single task for real server-side raster band validity and projection.
   CI cannot authenticate GEE; a passing synthetic run is insufficient.
2. Develop resumable region/time export manifest and adaptive task sizing
   before >400 cells, let alone 166,414 × 5 years. Do not launch tens of
   thousands of per-day per-cell requests. Use regional time-block processing.
3. Complete 2021–2025 meteorology at chosen representative cities with
   storm-independent exposure and overlap audit; do not derive storms from
   Groundsource or treat unlabeled as nonflood.
4. Validate nominal 100m GHS_POP and BUILT-S sums against official native
   source projection and grid-total conservation before using population/area.
5. Complete at least two independent externally audited flood/non-flood
   observation sources for physical skill; reject source-family duplicates.
6. Hold out new cities/countries/climates/years/storms and report failures,
   sample coverage, PR-AUC, uncertainty, ECE and failure domains.
7. Adaptation proxies must not be described as measured sewer resilience,
   causal effects, or an actual 10km hydraulic model.

Changes in this module do not update or submit task definitions in the
separate read-only `Global_flooding` project.
