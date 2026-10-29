"""Physical flood evidence protocol and fail-closed standardized reference loader.

This is NOT a remote sensing classifier. Previously downloaded rasters/shapes
require case-specific extraction/QA before passing their measurements here.
"""
from __future__ import annotations
from pathlib import Path
import csv
import numpy as np
import pandas as pd
from pyproj import Transformer

COLUMNS=["source_record_id","source_family","observation_date","longitude","latitude",
         "observation_type","pluvial_class","valid_spatiotemporal_coverage",
         "independent_source_confirmed","reviewer_id","evidence_uri",
         "location_precision_m","flood_observed"]
OBS_TYPES={"FIELD_OBSERVATION","IN_SITU_SENSOR","SAR_VERIFIED","OPTICAL_VERIFIED",
           "OFFICIAL_EVENT_LOCATION"}
PLUVIAL={"CONFIRMED_PLUVIAL","POSSIBLE_PLUVIAL","RIVERINE","COASTAL","MIXED","UNKNOWN"}

def template(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(COLUMNS)

def source_inventory(directories,max_files=1200):
    """Read-only bounded file metadata, NOT validation or extraction."""
    allowed={".shp",".gpkg",".geojson",".csv",".parquet",".tif",".tiff",".nc",
             ".nc4",".zip",".xlsx",".xls"}
    records=[]
    for label,root in directories:
        p=Path(root)
        if not p.exists():
            records.append({"source":label,"path":str(p),"status":"ABSENT","bytes":None})
            continue
        if p.is_file():files=[p]
        else:
            files=[]
            for q in p.rglob("*"):
                if q.is_file() and q.suffix.lower() in allowed:
                    files.append(q)
                    if len(files)>=max_files:break
        for q in files:
            records.append({"source":label,"path":str(q),
                            "status":"PRESENT_METADATA_ONLY","bytes":q.stat().st_size,
                            "suffix":q.suffix.lower()})
    return pd.DataFrame(records)

def validate_reference(data,grid,high_grid_days,day_tolerance=1):
    """Validate independently vetted location/date observations on 10km cells.

    Only rows explicitly reviewed with external lineage, valid time/space
    observation and verifiable evidence are used. No global accuracy claim.
    """
    if not 0<=day_tolerance<=3:raise ValueError("day_tolerance must be 0..3")
    d=pd.read_csv(data,dtype={"source_record_id":"string","source_family":"string"})
    missing=set(COLUMNS)-set(d)
    if missing:raise ValueError("Missing physical reference fields: "+str(sorted(missing)))
    if d.source_record_id.isna().any() or d.source_record_id.duplicated().any():
        raise ValueError("Physical record identifiers missing/duplicated")
    date=pd.to_datetime(d.observation_date,errors="coerce",format="mixed")
    lon=pd.to_numeric(d.longitude,errors="coerce")
    lat=pd.to_numeric(d.latitude,errors="coerce")
    prec=pd.to_numeric(d.location_precision_m,errors="coerce")
    method=d.observation_type.astype(str).str.upper().str.strip()
    cls=d.pluvial_class.astype(str).str.upper().str.strip()
    if not method.isin(OBS_TYPES).all():raise ValueError("Unknown physical observation_type")
    if not cls.isin(PLUVIAL).all():raise ValueError("Unknown pluvial_class")
    def truth(column):
        s=d[column].astype(str).str.upper().str.strip()
        if not s.isin(["YES","NO"]).all():raise ValueError(column+" must be YES/NO")
        return s.eq("YES")
    observed=truth("flood_observed")
    covered=truth("valid_spatiotemporal_coverage")
    independent=truth("independent_source_confirmed")
    quality=(date.notna()&lon.between(-180,180)&lat.between(-90,90)&
             prec.notna()&prec.between(0,10000)&
             d.reviewer_id.notna()&d.reviewer_id.astype(str).str.strip().ne("")&
             d.evidence_uri.notna()&d.evidence_uri.astype(str).str.strip().ne("")&
             covered&independent)
    if (observed&~covered).any():raise ValueError("Flood observed without coverage")
    # Unlike cloud-free pixels, an asserted genuine non-flood row requires an
    # explicit dedicated negative-observation protocol outside this interface.
    if (~observed).any():
        raise ValueError("Do not encode NO_FLOOD from non-detection. Use separate monitored-negative protocol.")
    if not quality.all():
        bad=d.loc[~quality,"source_record_id"].astype(str).head(15).tolist()
        raise ValueError("Unreviewed or invalid physical observations: "+str(bad))
    d=d.copy();d["date"]=date.dt.normalize()
    to_xy=Transformer.from_crs("EPSG:4326","EPSG:6933",always_xy=True)
    xx,yy=to_xy.transform(lon.to_numpy(),lat.to_numpy())
    gx=np.floor(xx/10000).astype(int);gy=np.floor(yy/10000).astype(int)
    d["grid_id"]=[f"{x}_{y}" for x,y in zip(gx,gy)]
    if grid.grid_id.duplicated().any():raise ValueError("Duplicate study grid")
    d["in_GF10"]=d.grid_id.isin(set(grid.grid_id.astype(str)))
    d["physically_confirmed_pluvial"]=cls.eq("CONFIRMED_PLUVIAL")
    positives=d[d.in_GF10 & d.physically_confirmed_pluvial].copy()
    high=high_grid_days[["grid_id","date"]].drop_duplicates().copy()
    high["date"]=pd.to_datetime(high.date).dt.normalize()
    high["grid_id"]=high.grid_id.astype(str)
    linked=[]
    for step in range(-day_tolerance,day_tolerance+1):
        observed_dates=positives[["source_record_id","grid_id","date"]].copy()
        observed_dates["date"]=observed_dates.date+pd.Timedelta(days=step)
        found=observed_dates.merge(high,on=["grid_id","date"],how="inner")
        linked.extend(found.source_record_id.astype(str).tolist())
    detected=set(linked)
    positives["news_matches_within_window"]=positives.source_record_id.astype(str).isin(detected)
    summary={
        "status":"CASE_STUDY_EXTERNAL_POSITIVE_SUPPORT_NOT_GLOBAL_ACCURACY",
        "independently_reviewed_reference_rows":len(d),
        "within_urban_gf10":int(d.in_GF10.sum()),
        "confirmed_pluvial_in_gf10":len(positives),
        "confirmed_pluvial_with_high_news":int(positives.news_matches_within_window.sum()),
        "confirmed_pluvial_without_high_news":int((~positives.news_matches_within_window).sum()),
        "sources":{str(k):int(v) for k,v in positives.source_family.value_counts().items()},
        "limitations":["Selection is not random global sample",
                       "Matched GF10 cell and date do not verify news polygon location",
                       "News absence is unlabeled, not ground truth nonflood",
                       "Only explicitly reviewed externally observed positives counted"]
    }
    return d,positives,summary
