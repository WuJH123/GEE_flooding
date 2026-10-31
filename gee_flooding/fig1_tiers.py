"""Publication-facing A/B/C geocode tiers and non-overclaiming de-dup layers.

Never equate a news UUID or same-grid-day cluster to an independent meteorological
storm. Dates from Groundsource describe reported interval, not measurement truth.
"""
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json

def assign_tiers(records):
    d=records.copy()
    area=pd.to_numeric(d.area_km2,errors="coerce")
    overlap=pd.to_numeric(d.primary_overlap,errors="coerce")
    n=pd.to_numeric(d.n_candidate_cells,errors="coerce")
    span=pd.to_numeric(d.report_span_days,errors="coerce")
    adequate=(area>0)&overlap.between(0,1)&(n>=1)&span.between(0,30)
    a=adequate&(area<=25)&(overlap>=.8)&(n<=4)&(span<=1)
    b=adequate&(area<=100)&(overlap>=.5)&(n<=16)&(span<=3)
    d["spatial_temporal_tier"]=np.select([a,b],["A","B"],default="C")
    d["tier_reason"]=np.select([a,b,~adequate],
              ["FINE_GEOCODE_SHORT_INTERVAL","MODERATE_GEOCODE_INTERVAL",
               "INCOMPLETE_GEOCODE_OR_DATE"],
              default="COARSE_GEOCODE_OR_LONG_INTERVAL")
    return d

def build_labels_release(root,raw_path,primary_path,tag="fig1_publication_v1"):
    import pyarrow.parquet as pq
    raw=pq.read_table(raw_path,columns=["uuid","area_km2","start_date","end_date"]).to_pandas()
    primary=pd.read_parquet(primary_path,columns=[
        "event_id","grid_id","date","n_candidate_cells","primary_overlap","geocode_quality"])
    if raw.uuid.duplicated().any():raise ValueError("Original UUID duplicate; abort before any dedup")
    if primary.event_id.duplicated().any():raise ValueError("One geocode must map to at most one primary GF10")
    if not primary.event_id.isin(raw.uuid).all():
        raise ValueError("Matched label not traceable to source UUID")
    core=primary.merge(raw.rename(columns={"uuid":"event_id"}),
                on="event_id",how="left",validate="one_to_one",indicator=True)
    if not core._merge.eq("both").all():raise ValueError("Groundsource provenance join incomplete")
    core=core.drop(columns="_merge")
    start=pd.to_datetime(core.start_date,errors="coerce").dt.normalize()
    end=pd.to_datetime(core.end_date,errors="coerce").dt.normalize()
    core["report_span_days"]=(end-start).dt.days
    core["date"]=pd.to_datetime(core.date,errors="raise").dt.normalize()
    if (core["date"]!=start).any():
        raise ValueError("Existing primary label date differs from original Groundsource start_date")
    core=assign_tiers(core)
    core["grid_day_key"]=core.grid_id.astype(str)+"|"+core.date.dt.strftime("%Y-%m-%d")
    # This collapse is one spatial-temporal observation unit, NOT proof of
    # one physical flood event, and is never a new meteorological storm ID.
    days=(core.groupby(["grid_id","date"],sort=True,as_index=False)
         .agg(raw_uuid_count=("event_id","nunique"),
              best_tier=("spatial_temporal_tier",lambda x:min(x)),
              any_high_geocode=("geocode_quality",
                               lambda x:bool(x.eq("HIGH_GEOCODE_SPECIFICITY").any()))))
    days=days.sort_values(["grid_id","date"]).reset_index(drop=True)
    prev=days.groupby("grid_id").date.diff().dt.days
    new_group=prev.isna()|prev.gt(1)
    days["grid_candidate_episode"]=(days.grid_id.astype(str)+"|"+
                                    new_group.cumsum().astype(str))
    episodes=(days.groupby("grid_candidate_episode",as_index=False)
              .agg(grid_id=("grid_id","first"),start=("date","min"),
                   end=("date","max"),distinct_days=("date","size"),
                   uuid_reports=("raw_uuid_count","sum")))
    out=safe_output(root,f"outputs/{tag}/labels")
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    core[["event_id","grid_id","date","area_km2","primary_overlap",
          "n_candidate_cells","report_span_days","geocode_quality",
          "spatial_temporal_tier","tier_reason","grid_day_key"]].to_parquet(
              out/"raw_uuid_tiers.parquet",index=False)
    days.to_parquet(out/"grid_day_observations.parquet",index=False)
    episodes.to_parquet(out/"candidate_grid_episodes.parquet",index=False)
    tier_counts={str(k):int(v) for k,v in core.spatial_temporal_tier.value_counts().items()}
    qc={"status":"PASS_NEWS_UNITS_AUDIT","raw_source_rows":len(raw),
        "matched_unique_uuids":len(core),"geocoded_grid_days":len(days),
        "candidate_contiguous_grid_episodes":len(episodes),
        "tier_counts":tier_counts,"AB_label_records":int(core.spatial_temporal_tier.isin(["A","B"]).sum()),
        "tier_definition":{"A":"area<=25km2; max-overlap>=0.8; <=4 matched urban cells; interval<=1 day",
                           "B":"area<=100km2; overlap>=0.5; <=16 matched urban cells; interval<=3 days",
                           "C":"all remaining mapped reports; preserve for auditing"},
        "independent_meteorological_storms":None,
        "unique_grid_day_policy":"Multiple raw UUIDs same grid and onset date are grouped as an observation unit, not claimed proven duplicates.",
        "grid_episode_policy":"Consecutive GF10 news grid-days, not proven separate floods or meteorological storms.",
        "date_precision_policy":"start/end span proxy is NOT independently verified reporting date accuracy.",
        "source_policy":"Geocoded article polygons are NOT physical inundation footprints"}
    if sum(tier_counts.values())!=len(core) or int(days.raw_uuid_count.sum())!=len(core):
        raise AssertionError("UUID or observation counts do not conserve")
    atomic_json(out/"label_tier_qc.json",qc)
    return qc
