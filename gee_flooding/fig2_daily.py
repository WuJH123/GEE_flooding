"""Figure 2 M03: strict DAILY GF10 weather panel from locally aggregated public data.

Daily analysis intervals are UTC. The M0 3h feature is a DAILY MAXIMUM of
true observed rolling 3h accumulations, NOT inferred from the daily total.
No need to store a global half-hour GF10 panel. Precipitation_cnt is NASA
daily valid half-hour count, never invented as 48. UNREPORTED != DRY.
No labels are used to identify meteorological exposure objects.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .fig2_prepare import weather_objects, STATIC
from .paths import safe_output, atomic_json


def read(path):
    p=Path(path)
    if p.suffix.lower()==".parquet":return pd.read_parquet(p)
    if p.suffix.lower()==".csv":return pd.read_csv(p)
    raise ValueError("Input must be pre-aggregated GF10 CSV or Parquet")


def build(root,grid_path,city_path,rain_path,peak3h_path,static_path,
          start,end,tag,p24=20.0,p3=10.0,radius=30,era_path=None,
          peak_definition="aligned_utc_3h_max"):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use immutable fig2_* tag")
    if peak_definition not in ("aligned_utc_3h_max","rolling_3h_max"):
        raise ValueError("Declare real 3h-window definition; never derive 3h from daily totals")
    begin=pd.Timestamp(start);finish=pd.Timestamp(end)
    if begin<pd.Timestamp("2021-01-01") or finish>pd.Timestamp("2025-12-31") or finish<begin:
        raise ValueError("Frozen Figure2 UTC scope: 2021-2025")
    dates=pd.date_range(begin,finish)
    grid=read(grid_path)
    expected={"grid_id","grid_x","grid_y","urban_fraction_2020"}
    if expected-set(grid):raise ValueError("Original frozen GF10 schema missing")
    grid=grid.copy();grid.grid_id=grid.grid_id.astype(str)
    if grid.grid_id.duplicated().any():raise ValueError("Duplicated GF10 grid_id")
    if len(grid)>2000 or len(grid)*len(dates)>2_000_000:
        raise ValueError("Split global scope by fixed GF10 geography; max 2m grid-days")
    city=read(city_path)
    if not {"grid_id","city_id"}<=set(city):raise ValueError("UCDB city crosswalk missing")
    city=city[["grid_id","city_id"]].copy();city.grid_id=city.grid_id.astype(str)
    if city.grid_id.duplicated().any():raise ValueError("Duplicate UCDB city crosswalk")
    grid=grid.merge(city,on="grid_id",how="left",validate="one_to_one")
    if grid.city_id.isna().any():raise ValueError("Missing city_id on frozen GF10")
    # The public NASA IMERG daily product's precipitation is mm/day.
    # Its precipitation_cnt is ACTUAL number of valid 30-min observations.
    rain=read(rain_path)
    req={"grid_id","date","rain_d_mm","precipitation_cnt"}
    if req-set(rain):raise ValueError("Daily IMERG GF10 lacks "+str(req-set(rain)))
    rain=rain.copy();rain.grid_id=rain.grid_id.astype(str)
    rain.date=pd.to_datetime(rain.date,errors="raise").dt.normalize()
    if rain.duplicated(["grid_id","date"]).any():
        raise ValueError("Duplicated NASA daily IMERG grid×UTC date")
    for field in ("rain_d_mm","precipitation_cnt"):
        rain[field]=pd.to_numeric(rain[field],errors="coerce")
        if not np.isfinite(rain[field]).all():raise ValueError("Null/nonfinite "+field)
    if (rain.rain_d_mm<0).any() or not rain.precipitation_cnt.between(0,48).all():
        raise ValueError("Daily NASA rain/count outside physical bounds")
    rain=rain.loc[rain.grid_id.isin(grid.grid_id)&
                  rain.date.between(begin-pd.Timedelta(days=7),finish)].copy()
    # Need seven previous COMPLETE UTC days for antecedent API at start.
    required_dates=pd.date_range(begin-pd.Timedelta(days=7),finish)
    expected_index=pd.MultiIndex.from_product(
        [grid.grid_id,required_dates],names=["grid_id","date"])
    observed=pd.MultiIndex.from_frame(rain[["grid_id","date"]])
    if len(rain)!=len(expected_index) or not observed.is_unique or not expected_index.difference(observed).empty:
        raise ValueError(f"Incomplete daily rain GF10/UTC coverage: {len(rain)} vs {len(expected_index)}")
    if rain.precipitation_cnt.lt(48).any():
        raise ValueError("IMERG daily valid retrieval count <48: not complete at declared GF10 cell-day")
    rain=rain.sort_values(["grid_id","date"])
    by_grid=rain.groupby("grid_id",sort=False)
    # strict EXCLUDES event day; 2020/12 history mandatory for 2021/01/01
    rain["api_7d_mm"]=by_grid.rain_d_mm.transform(
        lambda s:s.shift(1).rolling(7,min_periods=7).sum())
    rain["n_obs_7d"]=by_grid.precipitation_cnt.transform(
        lambda s:s.shift(1).rolling(7,min_periods=7).sum())
    rain=rain.loc[rain.date.between(begin,finish)].copy()
    rain=rain.rename(columns={"rain_d_mm":"rain_24h_mm",
                              "precipitation_cnt":"n_obs_24h"})
    # If maximum 3h precipitation is not available, FULL M0–M4 is blocked:
    # daily mean is NOT the six-bin rolling 3h maximum.
    peak=read(peak3h_path)
    k={"grid_id","date","rain_3h_mm"}
    if k-set(peak):raise ValueError("Independent daily maximum of rolling 3h is required")
    peak=peak[list(k)].copy()
    peak.grid_id=peak.grid_id.astype(str)
    peak.date=pd.to_datetime(peak.date,errors="raise").dt.normalize()
    if peak.duplicated(["grid_id","date"]).any():raise ValueError("Repeated 3h maximum grid×day")
    peak["rain_3h_mm"]=pd.to_numeric(peak.rain_3h_mm,errors="coerce")
    if not np.isfinite(peak.rain_3h_mm).all() or (peak.rain_3h_mm<0).any():
        raise ValueError("Invalid independent 3h maxima")
    w=rain.merge(peak,on=["grid_id","date"],validate="one_to_one",how="left")
    if w.rain_3h_mm.isna().any() or len(w)!=len(grid)*len(dates):
        raise ValueError("3h independent product does not completely cover GF10×UTC day")
    if not np.isfinite(w[["api_7d_mm","n_obs_7d"]]).all().all() or w.n_obs_7d.lt(336).any():
        raise ValueError("7d antecedent rainfall history incomplete")
    # Daily ERA5 inputs may be joined and shifted one UTC day; never use
    # event-day mean as a pre-onset causal predictor.
    optional=[]
    if era_path is not None:
        era=read(era_path)
        need={"grid_id","date","soil_water_0_7cm","soil_water_7_28cm","temperature_2m_c"}
        if need-set(era):raise ValueError("ERA5 daily source lacks "+str(need-set(era)))
        era=era[list(need)].copy()
        era.grid_id=era.grid_id.astype(str)
        era.date=pd.to_datetime(era.date,errors="raise").dt.normalize()
        if era.duplicated(["grid_id","date"]).any():raise ValueError("Duplicate ERA5 daily GF10")
        optional=["soil_water_0_7cm","soil_water_7_28cm","temperature_2m_c"]
        for key in optional:
            era[key]=pd.to_numeric(era[key],errors="coerce")
            if not np.isfinite(era[key]).all():raise ValueError("ERA5 daily missing "+key)
        for key in optional[:2]:
            if not era[key].between(0,1).all():raise ValueError("ERA5 soil volumetric water out of range")
        # Daily observations of PREVIOUS UTC day are available before event day.
        era["date"]=era["date"]+pd.Timedelta(days=1)
        w=w.merge(era,on=["grid_id","date"],how="left",validate="one_to_one")
        if w[optional].isna().any().any():
            raise ValueError("Missing previous-day ERA5 weather in frozen scope")
    w=w.merge(grid[["grid_id","grid_x","grid_y","city_id"]],
              on="grid_id",validate="many_to_one")
    storms=weather_objects(w,p24_min=p24,p3_min=p3,radius_km=radius)
    exposure=w.merge(storms,on=["grid_id","date"],how="inner",validate="one_to_one")
    if exposure.empty:raise ValueError("No storm-exposed GF10 grid-days; validate rain units")
    merged=Path(static_path)
    audit=merged.parent/"fig2_GF10_indicator_merge_qc.json"
    if not audit.is_file():
        audit=merged.parent/"fig2_local_static_qc.json"
    if not audit.is_file():raise ValueError("Static GF10 requires sibling audited QC")
    qa=json.loads(audit.read_text(encoding="utf-8"))
    if (qa.get("n_conflicts",qa.get("conflicts",1))
        or qa.get("frozen_grid_count")!=len(grid)):
        raise ValueError("Static source conflicts/incomplete grid")
    if audit.name=="fig2_local_static_qc.json" and qa.get("source_epoch_reference")!="frozen_surface_2020_2021":
        raise ValueError("Static local time-reference mismatch")
    static=read(merged)
    static.grid_id=static.grid_id.astype(str)
    if static.grid_id.duplicated().any() or set(static.grid_id)!=set(grid.grid_id):
        raise ValueError("Static file does not match declared frozen GF10")
    for col in STATIC:
        if col not in static:
            raise ValueError("Missing Figure2 mandatory static "+col)
    for col in ("hand_m","slope_deg","upstream_area_km2","vegetation_fraction","built_fraction_2020",
                "built_neighbor_density","built_fragmentation","built_growth_2000_2020"):
        if col not in static or not np.isfinite(pd.to_numeric(static[col],errors="coerce")).all():
            raise ValueError("M0–M4 cannot use incomplete static "+col)
    ref=static.set_index("grid_id").urban_fraction_2020
    baseline=grid.set_index("grid_id").urban_fraction_2020
    if not np.allclose(ref.reindex(baseline.index),baseline,atol=1e-5):
        raise ValueError("Frozen urban fraction disagrees")
    out=safe_output(root,"data/derived/"+tag)
    if out.exists():raise FileExistsError("Refusing to overwrite "+str(out))
    out.mkdir(parents=True,exist_ok=False)
    cols=["grid_id","date","storm_id","city_id","rain_24h_mm","rain_3h_mm","api_7d_mm"]
    exposure[cols+optional].to_parquet(out/"storm_exposure_weather.parquet",index=False)
    static.to_parquet(out/"static_grid_factors.parquet",index=False)
    static[["grid_id","built_fraction_2020","built_neighbor_density",
            "built_fragmentation","built_growth_2000_2020"]].to_parquet(
                out/"fig2_extended_grid_factors.parquet",index=False)
    static.to_parquet(out/"fig2_resilience_all_static_GF10.parquet",index=False)
    # Source provenance and full weather window, rather than pretending 3h is
    # computed from a daily total or equating news absence with dry conditions.
    manifest={
        "meteorology_source":"NASA GPM_3IMERGDF_07 Final daily + independent rolling 3h product",
        "exposure_sampling_rule":"all predeclared GF10 UTC days, independent rainfall threshold",
        "storms_independent_of_labels":True,
        "coverage_complete_within_scope":True,
        "spatial_scope":f"frozen GF10 selection, n={len(grid)}, NOT global by default",
        "start_date":str(begin.date()),"end_date":str(finish.date()),
        "time_basis":"UTC","rain_units":"mm",
        "rain3h_aggregation":peak_definition,
        "rain3h_limitation":"Aligned nonoverlapping 3h bins underestimate an unconstrained rolling 3h maximum" if peak_definition=="aligned_utc_3h_max" else "Rolling 3h maximum requires independently verified six-bin window algorithm",
        "rain3h_source_file":str(peak3h_path),
        "rain_daily_source_file":str(rain_path),
        "ERA5_previous_day_source_file":str(era_path) if era_path else None,
        "ERA5_antecedent_only":bool(era_path),
        "n_declared_grid_days":len(grid)*len(dates),
        "n_storm_exposures":len(exposure),
        "storm_object_method":"meteorological GF10 daily connected components, not verified synoptic storms",
        "n_storm_objects":int(storms.storm_id.nunique()),
        "p24_min_mm":p24,"p3_min_mm":p3,"radius_km":radius,
        "fixed_2020_2021_surface_not_historical_causal_exposure":True,
        "news_not_used_to_sample_weather":True,
        "no_flood_free_negatives":True,
        "source_warning":"For monthly/annual ERA5-EX do not use annual extrema as event-date exposures"}
    atomic_json(out/"fig2_weather_provenance.json",manifest)
    atomic_json(out/"fig2_daily_qc.json",
        {"status":"PASS_DAILY_GF10_M03_M04_NOT_PHYSICAL_TRUTH",
         "n_cells":len(grid),"days":len(dates),
         "n_exposure_rows":len(exposure),"n_storm_proxies":len(storms.storm_id.unique()),
         "daily_48_valid_required":True,"prior7_336_valid_required":True,
         "full_fig2_test_and_figure3_physical_gate":False})
    return manifest


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--grid-cities",type=Path,required=True)
    p.add_argument("--rain-daily",type=Path,required=True)
    p.add_argument("--rain-3h-max",type=Path,required=True)
    p.add_argument("--static",type=Path,required=True)
    p.add_argument("--start",default="2021-01-01")
    p.add_argument("--end",default="2025-12-31")
    p.add_argument("--tag",default="fig2_daily_pilot_v1")
    p.add_argument("--p24-min",type=float,default=20)
    p.add_argument("--p3-min",type=float,default=10)
    p.add_argument("--radius-km",type=float,default=30)
    p.add_argument("--era-daily",type=Path,help="Optional previous-day GF10 ERA5-Land daily source")
    p.add_argument("--rain3h-definition",choices=["aligned_utc_3h_max","rolling_3h_max"],
                   default="aligned_utc_3h_max")
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,a.grid,a.grid_cities,a.rain_daily,
                           a.rain_3h_max,a.static,a.start,a.end,a.tag,
                           a.p24_min,a.p3_min,a.radius_km,a.era_daily,
                           a.rain3h_definition),
                     indent=2,ensure_ascii=False))


if __name__=="__main__":main()
