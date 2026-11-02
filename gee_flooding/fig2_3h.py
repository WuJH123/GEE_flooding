"""M03 auxiliary local archive: daily max from 3-hourly *aligned* IMERG bins.

NOT an exact rolling 3-hour peak: requires 8 independent non-overlapping
UTC three-hour accumulation windows for every selected GF10-day. Explicitly
records this difference; full frozen paper uses this predeclared 3h definition
or validates the 3h rolling-vs-aligned discrepancy on independent events.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json


def collapse(root,source,tag):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use new immutable fig2_* tag")
    x=pd.read_parquet(source) if str(source).lower().endswith(".parquet") else pd.read_csv(source)
    req={"grid_id","timestamp_utc","precip_3h_mm"}
    if req-set(x):raise ValueError("3h archive lacks "+str(req-set(x)))
    x=x[list(req)].copy()
    utc=pd.to_datetime(x.timestamp_utc,utc=True,errors="raise")
    if utc.isna().any():raise ValueError("Invalid 3h UTC timestamp")
    if utc.dt.minute.ne(0).any() or utc.dt.hour.mod(3).ne(0).any():
        raise ValueError("Only aligned 00,03,...,21 UTC 3h time bins")
    x.grid_id=x.grid_id.astype(str)
    x["timestamp_utc"]=utc.dt.tz_convert(None)
    if x.duplicated(["grid_id","timestamp_utc"]).any():
        raise ValueError("Duplicated native 3h UTC bins")
    x.precip_3h_mm=pd.to_numeric(x.precip_3h_mm,errors="coerce")
    if not np.isfinite(x.precip_3h_mm).all() or x.precip_3h_mm.lt(0).any():
        raise ValueError("Invalid source 3h accumulation; source must be mm per 3h")
    x["date"]=x.timestamp_utc.dt.normalize()
    grouped=x.groupby(["grid_id","date"]).agg(
        n_3h_bins=("precip_3h_mm","size"),
        rain_3h_mm=("precip_3h_mm","max")).reset_index()
    if grouped.n_3h_bins.ne(8).any():
        raise ValueError("Incomplete source daily 8 aligned 3h bins; do not fill gaps")
    out=safe_output(root,"data/derived/"+tag)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    grouped[["grid_id","date","rain_3h_mm"]].to_parquet(
        out/"fig2_daily_max_aligned_3h_GF10.parquet",index=False)
    atomic_json(out/"fig2_daily_max3h_QC.json",dict(
        status="ALIGNED_3H_MAX_NOT_ROLLING_3H_MAX",
        n_GF10_days=len(grouped),n_3h_bins=int(len(x)),
        source_file=str(source),rain3h_units="mm",
        requires_rolling_3h_sensitivity_for_physical_short_duration_claims=True))
    return dict(n_GF10_days=len(grouped),n_3h_bins=len(x))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--tag",default="fig2_3h_daily_max_v1")
    a=p.parse_args(argv)
    print(json.dumps(collapse(a.root,a.input,a.tag),indent=2,ensure_ascii=False))
if __name__=="__main__":main()
