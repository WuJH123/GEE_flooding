# Research protocol — GEE_flooding

This is a standalone manuscript, distinct from the Global_flooding city–storm study. Target journal: Communications Earth & Environment.

## Estimand
Groundsource supplies geocoded news observations, NOT measured flood extent. An unreported grid-day is UNLABELED, not guaranteed flood-free. The initial model evaluates reported news vs unlabeled records; never call its scores calibrated true pluvial flood probability. Independent local flood observations with audited true negatives are required for physical-risk inference.

## Hypotheses
H1: Urban land-surface and terrain improve prediction beyond rainfall under joint city/storm holdouts.
H2: The added predictive value depends on geographic scale and setting.
H3: Missing news and geocode quality affect reported transferability.

## Immutable sources
All outputs and logs stay in E:\GEE_flooding. Old E:\Global_flooding can only be read, not overwritten. Never use the historical 20 km case-control or grid-day parquet as original Groundsource. Source is the five-column 2026 Zenodo Parquet; geocoder polygon area is NOT flood area. Frozen GF10 10 km EPSG:6933 grid may be reused as a read-only reference once Stage62b and Stage72 QC pass. GHSL SMOD urban share is NOT built-surface fraction.

## Stages and maturity
- P0.0 repository and provenance: implemented.
- P0.1 original Groundsource quality screen + 10 km primary geocode: implemented.
- P0.2 meteorology-derived independent storms + complete exposed universe: required input, NOT implemented.
- P0.3 spatial covariates including DEM/HAND and 2020–2021 land cover: required input, NOT implemented.
- P0.4 rainfall, rainfall+terrain, rainfall+terrain+surface ML ablation under joint city/storm holdout: implemented, proxy target only.
- P0.5 independently confirmed pluvial flood and non-flood validation: future mandatory study.
- P1.0 positive-unlabeled sensitivity and reporting selection analysis: future.
- P1.1 withheld country and climate-belt robustness, group bootstrap: future.
- P1.2 quality-tagged validated susceptibility maps: future.

## Leakage and scientific safeguards
Source events grouped by original UUID and geocode polygon; do not transform centroid into physical inundation point. Storm IDs must originate from meteorology, not news. Fixed 2020 urban surface must not be used for prospective pre-2020 prediction; restrict baseline to 2020+ weather exposures or use epoch-matched covariates. At most one attributed meteorological storm per grid-day in initial panel. Do not fill missing precipitation with zero. Compare M0, M1, M2 on identical heldout city+storm set. Do not interpret SHAP as causation. External city pluvial records and observed non-flood monitoring are necessary before publication claims.

## References
Zhao et al., Earth's Future (2026), doi:10.1029/2025EF007148. Groundsource: doi:10.5281/zenodo.18647054. Google Research (2026) already has Groundsource-driven flash flood forecasting, so algorithm selection alone is not novel.
