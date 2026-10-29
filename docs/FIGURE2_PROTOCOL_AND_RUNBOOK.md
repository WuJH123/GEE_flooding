# Figure 2 — transferability under extreme rainfall (2026-10-29)

## Research boundary and operational status

Independent Communications Earth & Environment manuscript. Figure 2 is NOT the Nature Cities
city–storm atmospheric-pathway analysis. Never write to E:\Global_flooding.

**Code status**: reproducible Figure2 *methods and bounded export pilot*, not an executed
global publication result. A GEE task in READY or RUNNING is not a downloaded observation.
Only synthetic unit tests can run in GitHub Actions. Real GF10 weather/static exports,
independently sourced reporting propensity, and physically verified pluvial positives AND
negatives are **not** established by this repository. Figure2 outputs carry an explicit
NEWS_PROXY status until those gates are satisfied.

## Science: five panels, same evaluation population

(a) IMERG-derived rainy-grid/day event universe (including unreported exposures), joined
to the frozen 10km equal-area GF10 domain, official UCDB city crosswalk and audited
Groundsource high-geocode-specificity UUIDs. The primary unit is grid × **meteorological
wet component**, with UTC grid-day exposure rows. Geo-coded news reports are neither
observed inundation locations nor measured flood footprints. Urban-only connected
components may split synoptic systems: a meteorological proxy, not a validated
storm-track catalogue.

(b) Sequential ablations evaluated on IDENTICAL held-out rows:
- M0 precipitation (24 h, 3 h maxima, previous 7 d);
- M1 + HAND and slope (MERIT-derived proxies; not an underground drainage model);
- M2 + frozen urban fraction (SMOD) and WorldCover vegetation share;
- M3 + GHSL 2020 built fraction, neighborhood built density and local spatial
  standard-deviation proxy for built fragmentation;
- M4 + 2000→2020 GHSL built fraction change;
- M5 optional externally audited inverse-coverage-weight *sensitivity* using the
  SAME M4 predictors. M5 is **NOT** an identified missing-data correction and
  cannot establish absolute event prevalence. It remains unavailable otherwise.

(c) Repeated group splits (seeds 42/43/44): unseen UCDB cities + unseen meteorological
storm IDs, unseen countries + storms, unseen Köppen macroclimate zones + storms,
unseen years + storms. Invalid splits are recorded with reasons; do not replace missing
groups with random row splits. Group-bootstrap interval uses storm clusters. Show PR-AUC
against random-news baseline, ROC-AUC and coverage in the accompanying CSV.

(d) Held-out **news-proxy** reliability diagram, Brier score, expected calibration
error and an optional external-physical ranking audit. A truly independent event
assessment must have verified flood AND observed nonflood, precise grid-day, explicit
pluvial identification, provenance and valid observation coverage. GFID/DFO record
coincidences are NOT valid physical labels, nor are queued GFD Earth Engine tasks.
Physical validation with sufficiently many verified cases supports ranking evidence,
NOT automatically calibrated true flood probability.

(e) Observed news-onset shares across HAND × built fraction strata in the high-rain
heldout subset. These are DESCRIPTIVE proxies; not counterfactual effects, SHAP
causality, or universal flood thresholds.

**Do not train on the 20km historical matched-control data.** The study uses 2021+
exposures for fixed 2020 GHSL/SMOD and 2021 ESA WorldCover. Such predictors should
not be construed as actual 2025 surface changes or pre-2021 historical conditions.
All training uses the same data rows, exposure thresholds and spatial units.

## Existing sources: verified in past local QC, no re-download

| Source | Local path / purpose |
| --- | --- |
| Frozen GF10 grid | E:\GEE_flooding\data\reference\grid10_urban_2020.parquet |
| Original Groundsource | E:\GEE_flooding\data\raw\groundsource_2026.parquet |
| High specificity label map | E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet |
| Label QC | E:\GEE_flooding\reports\qc\labels_qc.json |
| Figure1 UCDB grid crosswalk | E:\GEE_flooding\outputs\fig1_v1\fig1_grid_dominant_ucdb.parquet (change to finished v3 tag) |
| Figure1 city/continent/country/climate/eligibility audit | E:\GEE_flooding\outputs\fig1_v1\fig1_ucdb_city_sample_audit.csv (change to v3) |
| Official UCDB raw geometry | E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg |
| GFID archives | Can be reused for Fig1 catalogue agreement ONLY; never used as physical flood labels |

Do not assume Fig1_v3 is merged or its P0 findings have passed: check its actual
QC and code SHA before analysis.

## Open-access sources newly required for Figure 2

All four below are accessible from Earth Engine: no public raster needs to be
downloaded wholesale for a pilot. Exports to the user's own Drive need a registered
Earth Engine project and user authentication; **this chat has not run any GEE task**.

| Dataset | Exact Earth Engine ID | Role / limitation |
| --- | --- | --- |
| NASA GPM IMERG Final V07 | `NASA/GPM_L3/IMERG_V07` | 30-min precipitation **mm/h**, multiply each half hour by 0.5h for mm; 24h/3h rolling / antecedent 7d |
| MERIT Hydro | `MERIT/Hydro/v1_0_1` | `hnd`, `elv` slope; ~90m hydrologic proxies, not street microtopography |
| ESA WorldCover 2021 | `ESA/WorldCover/v200` | 10m `Map` vegetation classes, available 2021 only |
| GHSL BUILT-S epochs | `JRC/GHSL/P2023A/GHS_BUILT_S/2000` and `/2020` | m² built area per 100m pixel; temporal built fractions and context, not SMOD |

Official source/catalogue pages:
- https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
- https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S
- Groundsource: https://doi.org/10.5281/zenodo.18647054

Recommended *later* independent physical sources: quality-screened local official flood
and dry monitoring records with exact time, rainfall type, coverage and independence,
or completed GFD/Sentinel-1 event observation products **with real dry negatives**
and cloud/observation masks. GFD catalogue:
https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1
Many GFD events are DFO-derived and MODIS struggles with urban pluvial inundation;
they do not mechanically validate Groundsource labels.

## End-to-end bounded pilot workflow

### 0. Setup / audit; nothing writes to the old project

```powershell
Set-Location E:\GEE_flooding
git fetch origin
git pull --ff-only origin main
$PY = "E:\GEE_flooding\.venv\Scripts\python.exe"
& $PY -m pip install -e ".[test]"
& $PY -m pip install earthengine-api
& $PY -m pytest -q
& $PY -m gee_flooding --root E:\GEE_flooding inventory
& $PY -m gee_flooding --root E:\GEE_flooding summarize-labels
Test-Path E:\GEE_flooding\outputs\fig1_v1\fig1_grid_dominant_ucdb.parquet
```

### 1. Authenticate once for public GEE assets

```powershell
& $PY -m ee authenticate
& $PY -m ee set_project YOUR_REGISTERED_GEE_PROJECT_ID
```

If your ee CLI does not expose `set_project`, follow the current Earth Engine
Python authentication/project instructions. No credential is stored in GitHub.
Use **one small batch** first, avoid accidental global exports.

### 2. Pilot export: 50 GF10 cells × one UTC day, no task without --submit

```powershell
$GRID="E:\GEE_flooding\data\reference\grid10_urban_2020.parquet"
& $PY -m gee_flooding.fig2_gee --grid $GRID --mode static --start-row 0 --count 50
& $PY -m gee_flooding.fig2_gee --grid $GRID --mode weather --date 2023-08-01 --start-row 0 --count 50
# Submit only after reviewing dry-run and available GEE quota:
& $PY -m gee_flooding.fig2_gee --grid $GRID --mode static --start-row 0 --count 50 --submit
& $PY -m gee_flooding.fig2_gee --grid $GRID --mode weather --date 2023-08-01 --start-row 0 --count 50 --submit
```

Check task completion in https://code.earthengine.google.com/tasks and download
**completed** CSVs from the `GEE_flooding_Figure2` Google Drive folder into:
`E:\GEE_flooding\data\gee_exports\fig2_weather` and `...\fig2_static`.

The exporter is deliberately constrained to <=250 cells x **one day** per weather
task, for safe small pilots. It is NOT the scalable global production solution.
Do not launch 166,414 cells x 5 years by looping over all rows/days: that would
create a prohibitive number of GEE tasks. For publication-scale processing,
build/validate region-month task orchestration or full-tile IMERG raster mosaics
and distributed local extraction, with quotas and a resumable manifest first.

### 3. Assemble once the entire declared pilot coverage is downloaded

The example below requires 50 cells for **every UTC day** of August 2023, plus
the full seven-day antecedent precipitation history and one static CSV per cell.
A one-day export cannot satisfy a month-long model. Replace date/row selection
with the actual downloaded batch and full range. City crosswalk coverage is
mandatory: choose a batch where all cells have an official UCDB city mapping.

```powershell
$F1="E:\GEE_flooding\outputs\fig1_v1"
& $PY -m gee_flooding.fig2_prepare --root E:\GEE_flooding `
 --grid $GRID --grid-cities "$F1\fig1_grid_dominant_ucdb.parquet" `
 --weather-dir "E:\GEE_flooding\data\gee_exports\fig2_weather" `
 --static-dir "E:\GEE_flooding\data\gee_exports\fig2_static" `
 --start 2023-08-01 --end 2023-08-31 --start-row 0 --count 50 `
 --p24-min 20 --p3-min 10 --radius-km 30
```

This rejects missing grid-days, missing GEE half-hour bins, duplicate exports,
null predictor pixels and disconnected official-city grids. Each storm ID comes
from IMERG wet-space-time connected components, **not** Groundsource reporting.

### 4. Assemble reported-vs-unlabeled weather panel

```powershell
& $PY -m gee_flooding --root E:\GEE_flooding panel `
 --weather E:\GEE_flooding\data\derived\storm_exposure_weather.parquet `
 --static E:\GEE_flooding\data\derived\static_grid_factors.parquet `
 --labels E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet
```

The existing `panel` command refuses to overwrite the output. A smoke panel
lacking sufficient positives/storm/city diversity correctly stops rather than
printing plausible research scores.

### 5. M0–M4, M5 sensitivity, external audit and Figure 2a–e

```powershell
& $PY -m gee_flooding.fig2 --root E:\GEE_flooding `
 --panel E:\GEE_flooding\outputs\panels\storm_exposure_with_news_labels.parquet `
 --contract E:\GEE_flooding\data\derived\fig2_weather_provenance.json `
 --extended E:\GEE_flooding\data\derived\fig2_extended_grid_factors.parquet `
 --grid-cities "$F1\fig1_grid_dominant_ucdb.parquet" `
 --cities "$F1\fig1_ucdb_city_sample_audit.csv" --tag fig2_v1
```

Optional independently verified observations (after audit):
`--physical E:\GEE_flooding\data\external\pluvial_physical_audit.csv`
and `--require-physical` for the strict publication gate.

External physical CSV must contain:
`grid_id,date,sensor,valid_observation,flood_observed,source_independent,pluvial_confirmed`.
Do not mark GFID archive concordance, GFD catalogue events or unreported news days
as verified physical negatives. The external evaluation is restricted to WITHHELD
cities/storms; adequate positives and negatives are required.

M5 requires independent exogenous `reporting_propensity` in the **panel** (0.05–1),
and `reporting_propensity_external_audit=true` in weather contract. Never
derive the M5 weights from the evaluation outcome or invent coverage rates.
M5 assesses selection sensitivity, not corrected incidence.

Outputs under `E:\GEE_flooding\outputs\fig2_v1` include
`Figure2_news_proxy.png/.pdf`, ablation/transfer metrics,
failed split register, withheld predictions, optionally external matched audit,
and `fig2_qc_and_provenance.json`. The tag directory is immutable.

## Hard science gates and P0 issues

1. **Independent universe**: meteorological selection precedes any news join.
   Whole declared cell x day coverage and 48+336 half-hour checks pass.
   A handful of downloaded CSVs is a pilot, not global representativeness.
2. **Figure1 handoff**: current final Figure1 city provenance and eligibility
   must be reconciled, including GFID lineage and city coverage selection.
3. **Scale**: 10km is not a physical street inundation unit; do not validate
   urban microdrainage performance or treat MERIT HAND as curb-level elevation.
4. **Generalization**: record supported target-positive/test groups, all
   seeds, missing country/climate labels, CI and failed splits. Require
   sufficient genuine withheld positive exposures for any CEE claim.
5. **Selection & date uncertainty**: Groundsource reporting bias, duplicates,
   delayed dates, geocode polygon ambiguity and multi-day onset tolerance
   need additional ±1/±3 day sensitivity, source-family, quality-stratum and
   surveillance-covariate tests before publication.
6. **Storm independence**: compare urban connected components to a real
   external storm-object tracker; test 10/20/30mm and 20/30/50km thresholds.
7. **Physical evaluation**: independent, locally verifiable pluvial cases and
   observed dry negatives with observation coverage; verify sensor/news
   source independence. Without this, do NOT title the figure a validated
   flood susceptibility predictor or construct global risk probabilities.
8. **Reproducibility**: maintain source versions, UTC dates, task-completion
   manifests, holdout IDs, raster resolution, non-overwrite outputs and
   completed GitHub CI tests. No GEE exports run inside ChatGPT.

## Required publication-scale engineering upgrade

The bounded pilot GEE exporter is deliberately not a worldwide batch executor.
Before Figure 2 can be considered fully produced, implement globally tractable
IMERG time-window tasking, stratified city sampling, task resume/manifest state,
independent meteorological track validation, and external hydraulic/physical
positive-negative audit. None of these should be marked PASS based on synthetic
CI or on Figure1 GFID catalogue agreement.
