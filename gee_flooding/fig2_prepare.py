"""Build Figure2 exposures from COMPLETE GEE weather and static CSV exports.

A declared UTC date interval x frozen set of GF10 cells is required. This prevents
constructing an artificially high-quality sample from news-positive dates alone.
Meteorological component IDs are approximate storms, determined without news.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from .paths import safe_output, atomic_json

WEATHER=["rain_24h_mm","rain_3h_mm","api_7d_mm","n_obs_24h","n_obs_7d"]
STATIC=["hand_m","slope_deg","vegetation_fraction","built_fraction_2020",
        "built_neighbor_density","built_fragmentation","built_growth_2000_2020"]


def load_exports(directory, prefix):
    files=sorted(Path(directory).glob(prefix+"*.csv"))
    if not files:
        raise FileNotFoundError("No GEE CSV downloaded: "+str(directory)+"/"+prefix)
    frames=[]
    for file in files:
        x=pd.read_csv(file)
        if "grid_id" not in x:
            raise ValueError("Missing grid_id in "+str(file))
        if prefix=="f2_weather_":
            single=re.fullmatch(r"f2_weather_(\d{8})_\d{6}_\d{6}\.csv",file.name)
            weekly=re.fullmatch(r"f2_weather_week_(\d{8})_(\d{2})_\d{6}_\d{6}\.csv",file.name)
            if single:
                x["date"]=pd.to_datetime(single.group(1),format="%Y%m%d")
            elif weekly:
                if "date" not in x:raise ValueError("Weekly GEE CSV missing per-row UTC date")
                first=pd.to_datetime(weekly.group(1),format="%Y%m%d")
                days=int(weekly.group(2))
                if not 1<=days<=7:
                    raise ValueError("Invalid weekly weather export window")
                parsed=pd.to_datetime(x.date,errors="raise").dt.normalize()
                if not parsed.between(first,first+pd.Timedelta(days=days-1)).all():
                    raise ValueError("Weekly task contains dates outside declared window")
                x["date"]=parsed
            else:
                raise ValueError("Unrecognized UTC export filename: "+file.name)
        frames.append(x)
    return pd.concat(frames,ignore_index=True)


class UnionFind:
    def __init__(self,n):
        self.parent=np.arange(n,dtype=np.int64)
        self.rank=np.zeros(n,dtype=np.int8)

    def find(self,i):
        j=int(i)
        while self.parent[j]!=j:
            self.parent[j]=self.parent[int(self.parent[j])]
            j=int(self.parent[j])
        return j

    def union(self,i,j):
        a,b=self.find(i),self.find(j)
        if a==b:return
        if self.rank[a]<self.rank[b]:a,b=b,a
        self.parent[b]=a
        if self.rank[a]==self.rank[b]:self.rank[a]+=1


def weather_objects(df, p24_min=20.0, p3_min=10.0, radius_km=30):
    """3-D connected rainy grid-days with 1-day temporal tolerance.

    Not physically tracked storms; severed urban coverage can split an event.
    Dates and rainfall alone are used; news labels MUST NOT enter this routine.
    """
    if p24_min<=0 or p3_min<=0 or not 10<=radius_km<=50:
        raise ValueError("Invalid meteorological threshold/radius")
    selected=df.loc[(df.rain_24h_mm>=p24_min)|(df.rain_3h_mm>=p3_min)].copy()
    selected=selected.sort_values(["date","grid_id"]).reset_index(drop=True)
    if selected.empty:
        raise ValueError("No storm-exposed grid-days at thresholds")
    xy=selected[["grid_x","grid_y"]].to_numpy(dtype=float)*10000
    uf=UnionFind(len(selected))
    days={date:idx.to_numpy(dtype=int) for date,idx in
          selected.groupby("date",sort=True).groups.items()}
    radius=radius_km*1000
    sorted_days=sorted(days)
    for day in sorted_days:
        loc=days[day]
        if len(loc)>1:
            tree=cKDTree(xy[loc])
            for i,j in tree.query_pairs(r=radius):
                uf.union(int(loc[i]),int(loc[j]))
        other=day+pd.Timedelta(days=1)
        if other in days:
            nxt=days[other]
            first=cKDTree(xy[loc])
            second=cKDTree(xy[nxt])
            for i,hits in enumerate(first.query_ball_tree(second,r=radius)):
                for j in hits:uf.union(int(loc[i]),int(nxt[j]))
    groups=defaultdict(list)
    for i in range(len(selected)):
        groups[uf.find(i)].append(i)
    ids=np.empty(len(selected),dtype=object)
    for members in groups.values():
        ref=selected.iloc[min(members)]
        slug=str(ref.date.date())+"_"+str(ref.grid_id)
        digest=hashlib.sha256(slug.encode()).hexdigest()[:10]
        storm_id="imerg_cc_"+slug[:10].replace("-","")+"_"+digest
        ids[members]=storm_id
    selected["storm_id"]=ids
    return selected[["grid_id","date","storm_id"]]


def build(root, grid_path, grid_cities, labels, weather_dir, static_dir,
          start, end, start_row=0, count=50, p24_min=20, p3_min=10, radius_km=30, exposure_dir=None):
    grid=pd.read_parquet(grid_path)
    for col in ("grid_id","grid_x","grid_y","urban_fraction_2020"):
        if col not in grid:raise ValueError("GF10 reference missing "+col)
    if grid.grid_id.duplicated().any():raise ValueError("GF10 grid not unique")
    grid=grid.sort_values("grid_id").iloc[start_row:start_row+count].copy()
    if len(grid)!=count:raise ValueError("Expected selected grid count not present")
    grid["grid_id"]=grid.grid_id.astype(str)
    dates=pd.date_range(start,end,freq="D")
    if len(dates)==0 or dates.min()<pd.Timestamp("2021-01-01") or len(dates)>366:
        raise ValueError("Use a non-empty <=366-day UTC interval from 2021 onward per batch")
    city=pd.read_parquet(grid_cities,columns=["grid_id","city_id"])
    if city.grid_id.duplicated().any():raise ValueError("Duplicate UCDB grid crosswalk")
    city.grid_id=city.grid_id.astype(str)
    grid=grid.merge(city,on="grid_id",how="left",validate="one_to_one")
    if grid.city_id.isna().any():raise ValueError("Study subset includes GF10 cells not assigned to official UCDB cities")
    w=load_exports(weather_dir,"f2_weather_")
    s=load_exports(static_dir,"f2_static_")
    # Multiple completed time/space batches can share one folder.
    # Restrict to the PREDECLARED selection, then reject in-scope duplicates.
    w["grid_id"]=w.grid_id.astype(str)
    w["date"]=pd.to_datetime(w.date,errors="raise").dt.normalize()
    s["grid_id"]=s.grid_id.astype(str)
    w=w.loc[w.grid_id.isin(grid.grid_id)&w.date.isin(dates)].copy()
    s=s.loc[s.grid_id.isin(grid.grid_id)].copy()
    # The frozen grid is authoritative; static exports copy urban share for audit.
    if "urban_fraction_2020" in s:
        reference=grid[["grid_id","urban_fraction_2020"]]
        check=s[["grid_id","urban_fraction_2020"]].merge(
            reference,on="grid_id",how="left",suffixes=("_gee","_frozen"),
            validate="one_to_one")
        diff=(pd.to_numeric(check.urban_fraction_2020_gee,errors="coerce")-
              check.urban_fraction_2020_frozen).abs()
        if diff.isna().any() or diff.gt(1e-5).any():
            raise ValueError("GEE urban share conflicts with frozen GF10 reference")
        s=s.drop(columns=["urban_fraction_2020"])
    exposure=None
    if exposure_dir is not None:
        exposure=load_exports(exposure_dir,"f2_exposure_")
        exposure["grid_id"]=exposure.grid_id.astype(str)
        exposure=exposure.loc[exposure.grid_id.isin(grid.grid_id)].copy()
        required={"grid_id","population_count_2020","built_area_km2_2020",
                  "built_nres_area_km2_2020"}
        if required-set(exposure):raise ValueError("GHSL exposure columns missing")
        if exposure.grid_id.duplicated().any() or set(exposure.grid_id)!=set(grid.grid_id):
            raise ValueError("Incomplete or duplicate GHSL population context")
        for key in required-{"grid_id"}:
            exposure[key]=pd.to_numeric(exposure[key],errors="coerce")
            if not np.isfinite(exposure[key]).all() or exposure[key].lt(0).any():
                raise ValueError("Invalid GHSL exposure: "+key)
        if exposure.built_area_km2_2020.gt(100.01).any():
            raise ValueError("GHSL built area exceeds 100 km2 frozen GF10")
        if (exposure.built_nres_area_km2_2020>exposure.built_area_km2_2020+0.01).any():
            raise ValueError("GHSL nonresidential built area exceeds total")
    for name,frame,fields,key in [("weather",w,WEATHER,["grid_id","date"]),
                                  ("static",s,STATIC,["grid_id"])]:
        if set(fields)-set(frame):
            raise ValueError(name+" columns missing: "+str(sorted(set(fields)-set(frame))))
        frame["grid_id"]=frame.grid_id.astype(str)
        if frame.duplicated(key).any():
            raise ValueError("Duplicate "+name+" key")
        if set(frame.grid_id)-set(grid.grid_id):
            raise ValueError(name+" includes grid not in declared GF10 selection")
        for col in fields:
            frame[col]=pd.to_numeric(frame[col],errors="coerce")
            if not np.isfinite(frame[col]).all():
                raise ValueError(name+" has null/nonfinite "+col)
    w["date"]=pd.to_datetime(w.date).dt.normalize()
    if not w.date.isin(dates).all():
        raise ValueError("Weather export contains dates outside declared scope")
    expected=len(grid)*len(dates)
    if len(w)!=expected:
        raise ValueError(f"Incomplete grid x UTC day coverage: {len(w)} vs {expected}")
    if set(s.grid_id)!=set(grid.grid_id):
        raise ValueError("Static export must match all selected GF10 cells")
    for day,chunk in w.groupby("date"):
        if len(chunk)!=len(grid) or set(chunk.grid_id)!=set(grid.grid_id):
            raise ValueError("Incomplete GF10 coverage for "+str(day))
    if set(w.date)!=set(dates):
        raise ValueError("Missing meteorological UTC days")
    if (w.n_obs_24h<47.999).any() or (w.n_obs_7d<335.999).any():
        raise ValueError("IMERG incomplete half-hour windows; no zero-filling gaps")
    if w[["rain_24h_mm","rain_3h_mm","api_7d_mm"]].lt(0).any().any():
        raise ValueError("Negative IMERG rainfall")
    for col in ("vegetation_fraction","built_fraction_2020",
                "built_neighbor_density","built_fragmentation"):
        if not s[col].between(0,1).all():
            raise ValueError("Invalid raster fraction: "+col)
    w=w.merge(grid[["grid_id","grid_x","grid_y","city_id"]],on="grid_id",
              how="left",validate="many_to_one")
    catalog=weather_objects(w,p24_min,p3_min,radius_km)
    storms=w.merge(catalog,on=["grid_id","date"],how="inner",validate="one_to_one")
    if storms.empty:raise ValueError("No news-independent storm exposures")
    # Exact input required by the existing panel assembler. All weather reports
    # use UTC days. News reporting dates can differ from true event onsets.
    output_weather=safe_output(root,"data/derived/storm_exposure_weather.parquet")
    output_static=safe_output(root,"data/derived/static_grid_factors.parquet")
    output_extended=safe_output(root,"data/derived/fig2_extended_grid_factors.parquet")
    contract_path=safe_output(root,"data/derived/fig2_weather_provenance.json")
    output_resilience=safe_output(root,"data/derived/fig2_resilience_all_static_GF10.parquet")
    output_context=safe_output(root,"data/derived/fig2_ghsl_population_context_GF10.parquet")
    generated=[output_weather,output_static,output_extended,contract_path,output_resilience]
    if exposure is not None:generated.append(output_context)
    for p in generated:
        if p.exists():raise FileExistsError("Refusing to overwrite: "+str(p))
    output_weather.parent.mkdir(parents=True,exist_ok=True)
    weather_cols=["grid_id","date","storm_id","city_id","rain_24h_mm","rain_3h_mm","api_7d_mm"]
    # Preserve ERA5-Land antecedent features, with no missing-value zero-fill.
    extras=[key for key in ("soil_water_0_7cm","soil_water_7_28cm","temperature_2m_c")
            if key in storms]
    for key in extras:
        storms[key]=pd.to_numeric(storms[key],errors="coerce")
        if not np.isfinite(storms[key]).all():
            raise ValueError("ERA5-Land incomplete: "+key)
    storms[weather_cols+extras].to_parquet(output_weather,index=False)
    static=grid[["grid_id","urban_fraction_2020"]].merge(s,on="grid_id",
                                                          how="inner",validate="one_to_one")
    static[["grid_id","hand_m","slope_deg","urban_fraction_2020",
            "vegetation_fraction"]].to_parquet(output_static,index=False)
    if static.grid_id.duplicated().any():raise ValueError("Duplicated GF10 static key")
    static.to_parquet(output_resilience,index=False)
    if exposure is not None:exposure.to_parquet(output_context,index=False)
    static[["grid_id","built_fraction_2020","built_neighbor_density","built_fragmentation",
            "built_growth_2000_2020"]].to_parquet(output_extended,index=False)
    c={"meteorology_source":"NASA/GPM_L3/IMERG_V07",
       "storm_object_method":"IMERG urban-grid daily connected rainy components; proxy, not synoptic tracks",
       "storms_independent_of_labels":True,"coverage_complete_within_scope":True,
       "exposure_sampling_rule":"all predeclared urban-grid UTC days above independent rainfall threshold",
       "spatial_scope":f"GF10 lexical rows [{start_row},{start_row+count}) ONLY; not global",
       "start_date":str(dates[0].date()),"end_date":str(dates[-1].date()),
       "rain_units":"mm","time_basis":"UTC","n_declared_grid_days":expected,
       "n_storm_exposures":len(storms),"n_storm_objects":storms.storm_id.nunique(),
       "p24_min_mm":p24_min,"p3_min_mm":p3_min,"connect_radius_km":radius_km,
       "geocoded_news_not_in_storm_definitions":True,
       "fixed_2020_2021_surface_not_historical_causal_exposure":True,
       "event_independence_caveat":"Storm IDs are connected wet components, may split/merge meteorological systems.",
       "no_flood_free_negatives":True,
       "gf10_resilience_static_feature_count":len(static.columns)-1,
       "ghsl_exposure_context_available":exposure is not None,
       "era5_daily_indicators":extras,
       "gee_sampling_crs":"EPSG:4326",
       "population_context_caveat":"GHSL 100m population and built-surface sums require source-projection conservation QC"}
    atomic_json(contract_path,c)
    return c


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--grid-cities",type=Path,required=True)
    p.add_argument("--labels",type=Path,help="Reserved: labels never used to define storms")
    p.add_argument("--weather-dir",type=Path,required=True)
    p.add_argument("--static-dir",type=Path,required=True)
    p.add_argument("--exposure-dir",type=Path,help="Optional completed GHSL GHS_POP context CSVs")
    p.add_argument("--start",required=True,help="First inclusive UTC date")
    p.add_argument("--end",required=True,help="Last inclusive UTC date")
    p.add_argument("--start-row",type=int,default=0)
    p.add_argument("--count",type=int,default=50)
    p.add_argument("--p24-min",type=float,default=20)
    p.add_argument("--p3-min",type=float,default=10)
    p.add_argument("--radius-km",type=float,default=30)
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,a.grid,a.grid_cities,a.labels,a.weather_dir,a.static_dir,
                           a.start,a.end,a.start_row,a.count,a.p24_min,a.p3_min,a.radius_km,a.exposure_dir),
                     indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
