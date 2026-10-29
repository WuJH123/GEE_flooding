# GEE_flooding Figure 1 — public data, source lineage and restrictions

This is the INDEPENDENT Communications Earth & Environment project, NOT Nature Cities Global_flooding. All new files go to E:\GEE_flooding; old project paths are READ-ONLY.

## Panels (GEE manuscript only)
(a) 2020 GF10 city observation domain and high-geocode-specificity Groundsource news records.
(b) Original Groundsource -> mapped -> high/medium/low specificity and excluded reports.
(c) Annual news archive availability, NOT observed frequency of true floods.
(d) GFID source family spatiotemporal catalogue candidates, NOT real pluvial inundation validation. DFO is already part of GFID, so do not add DFO-GFID as independent evidence.
(e) Official UCDB city eligibility, split BEFORE training into training candidates, held-out city candidates and evidence-sparse cities.

## Nature journal Data availability benchmarks
- Tellman et al., Nature 2021, DOI https://doi.org/10.1038/s41586-021-03695-w : GFD products publicly released and mirrored in Earth Engine. GFD 913 events were selected from DFO. Pixel observations require cloud/clear-view QC. https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1
- Integrating social vulnerability into high-resolution global flood risk mapping, Nature Communications 2024, DOI https://doi.org/10.1038/s41467-024-47394-2 : openly available WorldPop and GDP, with some restricted commercial hazard inputs. These socioeconomic inputs are NOT necessary for initial Figure 1.
- Improving flood detection with large-scale dashboard camera data, Nature Communications 2026, DOI https://doi.org/10.1038/s41467-026-75938-1 : 311 reports have neighborhood and demographic reporting biases; flood sensor/visual evidence offers complementary validation.
- Waleed et al., Scientific Data 2026, DOI https://doi.org/10.1038/s41597-026-08338-1 : global 30m ML susceptibility map already exists. Distinguish our observation/label-quality study.
- USGS Global Flood Impacts Database GFID, DOI https://doi.org/10.5066/P135ARGI : GFID integrates 136642 DFO, DesInventar, EM-DAT and HANZE records. Representative coordinates and possible duplicate table do not establish precise flood location.

## Inputs already available — DO NOT DOWNLOAD AGAIN
1. E:\GEE_flooding\outputs\labels\groundsource_gf10_primary.parquet — original Groundsource UUID -> 10km dominant news-geocoder grid.
2. E:\GEE_flooding\data\reference\grid10_urban_2020.parquet — new independent frozen urban GF10 reference.
3. E:\GEE_flooding\reports\qc\labels_qc.json — geocode QC, 2646302 original records, 2202651 mapped as previously reported.
4. E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg — official UCDB (fixed boundary epoch different from GF10 2020).
5. E:\Global_flooding\grid10\reference_external\GFID\AggregatedFloodData.xlsx — source lineage families and candidate external catalogue coincidences.
6. E:\Global_flooding\koppen_geiger_tif\1991_2020\koppen_geiger_0p1.tif — climate strata, if this exact old path exists.
7. E:\Global_flooding\grid10\fig1_public\natural_earth\ne_110m_admin_0_countries.shp — world boundaries, if prior Figure1 source still exists.

Other already held data not required NOW:
- E:\数据集 DFO, CN-Floods, China county waterlogging, Henan, London: possible independent follow-up validation, after confirming exact flood type, time, location, coverage, source overlap and license.
- E:\Global_flooding\grid10\gfd_physical_v3: 8 READY GEE jobs are NOT valid physical-observation exports. Do not count these as satellite verification.
- E:\Global_flooding old M3 / GHSL / weather / MERIT / HAND: 20km products are not directly equal to new 10km labels.
- WorldPop, BUILT, GAIA, GISD30, WorldCover, DEM: later model predictor stages; NOT needed for this Figure1.

## Remaining truly missing evidence
For complete Figure1d and manuscript credibility, convert a SMALL selection of already-held independent physical flood observations (e.g. quality-controlled CN-Floods, Henan/London field observations, or genuinely completed GFD/Sentinel-1 exports) into an audited external validation table. Do not download the entire GFD image collection; Earth Engine already exposes it. If local regional evidence proves inadequate, acquire targeted official records, not another worldwide data stack.

Optional physical CSV schema: grid_id,date,sensor,valid_observation,flood_observed.
This interface only checks data fields and simple flags; it does NOT automatically prove a source independent of news or a real flood-free negative. Save accompanying validation protocol and QC.

## Reproducibility and status
Execute the NEW project's fig1 command and save outputs only under E:\GEE_flooding\outputs\fig1_v1. Expected: Figure1_GEE_observation.png (300 dpi), PDF, annual/UCDB audit tables, GFID candidate parquet, provenance JSON. Current QC is always DRAFT_NEEDS_INDEPENDENT_PHYSICAL_VALIDATION; do not claim final Nature-validated evidence or real flood prediction probabilities.
