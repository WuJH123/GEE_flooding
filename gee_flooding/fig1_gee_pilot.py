"""Select bounded, reproducible Figure 1 IMERG pilot grid-days from A/B/C.

The sample is for an OBSERVATION consistency check. It does not select or
claim independent storm IDs, and no-report dates are not flood-free labels.
"""
from pathlib import Path
import json
import pandas as pd
from .paths import safe_output,atomic_json

def prepare(root,tier_path,grid_path,tag="fig1_pilot_r1",n=24,seed=42,
            paired_controls=False):
    if not 1<=n<=100:raise ValueError("Pilot maximum is 100; never bulk submit")
    d=pd.read_parquet(tier_path,columns=["grid_id","date","spatial_temporal_tier"])
    d["date"]=pd.to_datetime(d.date).dt.normalize()
    d=d[d.date.dt.year.between(2001,2025)]
    if d.empty:raise ValueError("No dates in approved meteorological archive")
    tier_order=pd.Categorical(d.spatial_temporal_tier,categories=["A","B","C"],
                               ordered=True)
    d=d.assign(_tier=tier_order).sort_values(["grid_id","date","_tier"])
    days=d.drop_duplicates(["grid_id","date"],keep="first")[
        ["grid_id","date","spatial_temporal_tier"]].copy()
    grid=pd.read_parquet(grid_path,columns=[
       "grid_id","grid_x","grid_y","longitude","latitude"])
    if grid.grid_id.duplicated().any():raise ValueError("Duplicate study grid")
    days=days.merge(grid,on="grid_id",how="left",validate="many_to_one")
    if days.grid_x.isna().any():raise ValueError("Unknown original study grid ID")
    days["period"]=pd.cut(days.date.dt.year,bins=[2000,2018,2023,2025],
              labels=["GFD_2001_2018","DEV_2019_2023","HOLDOUT_2024_2025"])
    days["hemisphere"]=days.latitude.ge(0).map({True:"N",False:"S"})
    # Sample each tier x era x hemisphere stratum; do not use reported future
    # news to determine development-city eligibility.
    import numpy as np
    groups=list(days.groupby(["spatial_temporal_tier","period","hemisphere"],
                             observed=True))
    result=[]
    quota=max(1,n//max(len(groups),1))
    for _,g in groups:
        result.append(g.sample(n=min(quota,len(g)),random_state=seed))
    sample=pd.concat(result,ignore_index=True)
    if len(sample)<n:
        rem=days.loc[~days.set_index(["grid_id","date"]).index.isin(
            sample.set_index(["grid_id","date"]).index)]
        if len(rem):
            sample=pd.concat([sample,rem.sample(min(n-len(sample),len(rem)),
                       random_state=seed+1)],ignore_index=True)
    if len(sample)>n:sample=sample.sample(n=n,random_state=seed)
    sample=sample.sort_values(["period","date","grid_id"]).reset_index(drop=True)
    sample["sample_role"]="REPORTED_NEWS_DAY"
    sample["pair_id"]=["F1PAIR_%04d"%(i+1) for i in range(len(sample))]
    if paired_controls:
        # Same-grid same-season reference; NEVER pretend that no news = no flood.
        known=set(zip(days.grid_id.astype(str),days.date.dt.strftime("%Y-%m-%d")))
        comparisons=[]
        for rec in sample.itertuples(index=False):
            reference=None
            for offset in (28,-28,35,-35,21,-21):
                probe=rec.date+pd.Timedelta(days=offset)
                if probe.year!=rec.date.year:continue
                # reject all observed reports in +/- 3 days of reference
                nearby=[(str(rec.grid_id),(probe+pd.Timedelta(days=j)).strftime("%Y-%m-%d"))
                        for j in range(-3,4)]
                if not any(t in known for t in nearby):
                    reference=probe;break
            if reference is None:continue  # observed row remains in sample
            record={k:getattr(rec,k) for k in sample.columns}
            record["date"]=reference
            record["sample_role"]="UNLABELED_SAME_GRID_SEASON"
            comparisons.append(record)
        if comparisons:
            sample=pd.concat([sample,pd.DataFrame(comparisons)],ignore_index=True)
    # pair first then chronology; the first 12 EE rows contain observed/control
    # together when pairs are available, not only reported news rows.
    sample["role_order"]=sample.sample_role.map({
        "REPORTED_NEWS_DAY":0,"UNLABELED_SAME_GRID_SEASON":1})
    sample=sample.sort_values(["pair_id","role_order","date"]).reset_index(drop=True)
    sample["date"]=sample.date.dt.strftime("%Y-%m-%d")
    sample["pilot_id"]=["F1P_%04d"%(i+1) for i in range(len(sample))]
    sample["date_utc_policy"]="UTC_DAY_NEWS_ONSET_PROXY_OR_REFERENCE"
    sample["gfd_catalogue_period"]=sample["period"].eq("GFD_2001_2018")
    dest=safe_output(root,f"outputs/{tag}/gee")
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True,exist_ok=False)
    sample[["pilot_id","pair_id","sample_role","grid_id","grid_x","grid_y",
        "longitude","latitude","date","spatial_temporal_tier","period",
        "hemisphere","date_utc_policy","gfd_catalogue_period"]].to_csv(
            dest/"fig1_imerg_pilot_manifest.csv",index=False)
    qc={"status":"PILOT_ONLY_NO_PHYSICAL_VALIDATION",
        "n":len(sample),"n_reported_days":int(sample.sample_role.eq("REPORTED_NEWS_DAY").sum()),"n_unlabeled_reference_days":int(sample.sample_role.eq("UNLABELED_SAME_GRID_SEASON").sum()),"paired_controls":bool(paired_controls),"seed":seed,"n_requested":n,
        "by_tier":sample.spatial_temporal_tier.value_counts().to_dict(),
        "by_period":sample.period.astype(str).value_counts().to_dict(),
        "data_source":"Frozen GF10 and original Groundsource news dates",
        "limitations":["Stratified pilot, NOT global representative physical validation",
                       "IMERG rainfall does NOT prove inundation",
                       "No-report locations and days are unlabeled",
                       "No storm identification is inferred"]}
    atomic_json(dest/"pilot_manifest_qc.json",qc)
    return qc

def run_gee(project,manifest,description="FIG1_IMERG_V07_PILOT",submit=False,
            max_rows=12,drive_folder="GEE_flooding_fig1_validation"):
    """One bounded, auditable GEE table export; dry-run never contacts EE."""
    if not 1<=max_rows<=25:raise ValueError("GEE request >25 rows: split manually")
    data=pd.read_csv(manifest)
    req={"pilot_id","grid_id","grid_x","grid_y","date"}
    if req-set(data):raise ValueError("Pilot manifest missing: "+str(req-set(data)))
    if data.pilot_id.duplicated().any():raise ValueError("Duplicate pilot ids")
    data["date"]=pd.to_datetime(data.date,errors="raise",format="%Y-%m-%d")
    if not data.date.dt.year.between(2001,2025).all():raise ValueError("Unexpected year")
    data=data.iloc[:max_rows].copy()
    dry={"status":"DRY_RUN_NOT_SUBMITTED" if not submit else "SUBMISSION_REQUESTED",
         "rows":len(data),"rows_limit":25,"project":project,
         "description":description,
         "imerg_asset":"NASA/GPM_L3/IMERG_V07",
         "era5_asset":"ECMWF/ERA5_LAND/HOURLY",
         "rain_band":"precipitation","unit_conversion":"mm/h * 0.5 hours per IMERG image",
         "observation_coverage":"count all available half-hour frames vs expected 48/day, 336/7days",
         "date_window":"news-onset UTC day; not independently verified flood timing",
         "physical_verification":False}
    if not submit:return dry
    import ee
    ee.Initialize(project=project)
    output=[]
    for r in data.itertuples(index=False):
        day=ee.Date(r.date.strftime("%Y-%m-%d"))
        poly=ee.Geometry.Rectangle(
            [int(r.grid_x)*10000,int(r.grid_y)*10000,
             (int(r.grid_x)+1)*10000,(int(r.grid_y)+1)*10000],
            proj="EPSG:6933",geodesic=False)
        rain=ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(
            day,day.advance(1,"day")).select("precipitation")
        prior=ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(
            day.advance(-7,"day"),day).select("precipitation")
        # Avoid empty collection reduction: availability is explicitly reported;
        # valid months can be QC'd by n_frames, not by silently assuming zero.
        rainday=rain.sum().multiply(.5).rename("p24_mm")
        rainprior=prior.sum().multiply(.5).rename("p7ante_mm")
        mean=rainday.addBands(rainprior).reduceRegion(
            reducer=ee.Reducer.mean(),geometry=poly,scale=11132,
            maxPixels=10000,crs="EPSG:6933")
        soil=ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").filterDate(
            day.advance(-1,"day"),day).select(
                "volumetric_soil_water_layer_1")
        soil_mean=ee.Algorithms.If(soil.size().gt(0),soil.mean().reduceRegion(
             reducer=ee.Reducer.mean(),geometry=poly,scale=11132,
             maxPixels=10000,crs="EPSG:6933").get("volumetric_soil_water_layer_1"),None)
        feature=ee.Feature(poly.centroid(100),{
          "pilot_id":str(r.pilot_id),"grid_id":str(r.grid_id),
          "pair_id":str(getattr(r,"pair_id","")),
          "sample_role":str(getattr(r,"sample_role","UNSPECIFIED")),
          "date":r.date.strftime("%Y-%m-%d"),
          "p24_mm":mean.get("p24_mm"),
          "p7ante_mm":mean.get("p7ante_mm"),
          "n_imerg_24h":rain.size(),
          "n_imerg_prior7d":prior.size(),
          "soil_moisture_ante1d_m3m3":soil_mean,
          "n_era5_ante1d":soil.size(),
          "data_status":"METEOROLOGY_ONLY_NOT_FLOOD_TRUTH"
        })
        output.append(feature)
    task=ee.batch.Export.table.toDrive(
         collection=ee.FeatureCollection(output),
         description=description,folder=drive_folder,fileFormat="CSV",
         selectors=["pilot_id","pair_id","sample_role","grid_id","date","p24_mm","p7ante_mm",
                    "n_imerg_24h","n_imerg_prior7d",
                    "soil_moisture_ante1d_m3m3","n_era5_ante1d","data_status"])
    task.start()
    dry["task_id"]=task.id
    dry["status"]="SUBMITTED_REQUIRES_GEE_TASK_SUCCESS_AND_CSV_DOWNLOAD"
    dry["drive_folder"]=drive_folder
    return dry
