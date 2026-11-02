"""Compute exact six-bin rolling 3h IMERG Final rainfall, save DAILY maxima only.

Input: locally cropped GF10×30min records precipitation_rate_mm_h (mm/hr).
No long-term half-hour panel stored in output. Data must start 2.5 hours
before first target UTC day and include every half-hour through last day.
Six timestamps form a trailing 3h window; observed source units mm/h*0.5h.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json


def build(root,sources,start,end,tag):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use immutable fig2_* tag")
    begin=pd.Timestamp(start);finish=pd.Timestamp(end)
    if begin>finish:raise ValueError("Date order invalid")
    paths=[Path(x) for x in sources]
    if not paths or any(not x.is_file() for x in paths):
        raise FileNotFoundError("Half-hour GF10 inputs missing")
    parts=[]
    for p in paths:
        x=pd.read_parquet(p) if p.suffix.lower()==".parquet" else pd.read_csv(p)
        need={"grid_id","timestamp_utc","precipitation_rate_mm_h"}
        if need-set(x):raise ValueError("Half-hour file lacks "+str(need-set(x)))
        parts.append(x[list(need)])
    a=pd.concat(parts,ignore_index=True)
    a.grid_id=a.grid_id.astype(str)
    a.timestamp_utc=pd.to_datetime(a.timestamp_utc,utc=True,errors="raise").dt.tz_localize(None)
    if a.duplicated(["grid_id","timestamp_utc"]).any():
        raise ValueError("Duplicated GF10 half-hour timestamp across source files")
    a.precipitation_rate_mm_h=pd.to_numeric(a.precipitation_rate_mm_h,errors="coerce")
    if not np.isfinite(a.precipitation_rate_mm_h).all() or a.precipitation_rate_mm_h.lt(0).any():
        raise ValueError("NASA mm/h rate is missing or negative")
    if a.timestamp_utc.dt.second.ne(0).any() or ~a.timestamp_utc.dt.minute.isin([0,30]).all():
        raise ValueError("NASA source must have aligned UTC half-hour timestamps")
    dates=pd.date_range(begin,finish)
    start_time=begin-pd.Timedelta(minutes=150)
    end_time=finish+pd.Timedelta(hours=23,minutes=30)
    expected_times=pd.date_range(start_time,end_time,freq="30min")
    out=[]
    for gid,part in a.groupby("grid_id"):
        part=part.set_index("timestamp_utc").sort_index()
        selected=part.reindex(expected_times)
        if selected.precipitation_rate_mm_h.isna().any():
            raise ValueError(f"Incomplete 30-min source for GF10 {gid} [{start},{end}]")
        rain=selected.precipitation_rate_mm_h*0.5
        peak=rain.rolling(6,min_periods=6).sum().loc[begin:end_time]
        peakdaily=peak.groupby(peak.index.normalize()).max()
        if len(peakdaily)!=len(dates):
            raise ValueError("No complete six-bin rolling 3h maxima")
        for d,v in peakdaily.items():
            out.append(dict(grid_id=gid,date=d,rain_3h_mm=float(v)))
    frame=pd.DataFrame(out)
    output=safe_output(root,"data/derived/"+tag)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True,exist_ok=False)
    frame.to_parquet(output/"fig2_daily_rolling_3h_max_GF10.parquet",index=False)
    atomic_json(output/"fig2_rolling3h_QC.json",dict(
        status="TRUE_6_CONSECUTIVE_30MIN_ROLLING_3H_MAX",
        n_gf10_days=len(frame),n_GF10=frame.grid_id.nunique(),
        date_start=str(begin.date()),date_end=str(finish.date()),
        source_files=[str(p) for p in paths],
        complete_30min_required=True,
        precipitation_source_units="mm/hour",accumulation_factor_hours=.5,
        no_global_half_hour_output=True))
    return dict(n_gf10_days=len(frame),n_GF10=frame.grid_id.nunique())


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--input-dir",type=Path,required=True)
    p.add_argument("--glob",default="**/fig2_CF_halfhour_GF10.parquet")
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--tag",default="fig2_rolling3h_v1")
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,sorted(a.input_dir.glob(a.glob)),
                           a.start,a.end,a.tag),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
