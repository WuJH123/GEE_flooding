"""Merge independently extracted GF10 daily NetCDF batches without overlap/leakage.

This is a file-level operation on actual GF10 records, not an unverified
nearest-neighbor assignment from native 0.1-degree coordinates.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json


def merge(root,sources,tag):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use immutable fig2_* tag")
    sources=[Path(x) for x in sources]
    if not sources or any(not x.is_file() for x in sources):
        raise ValueError("Source list contains nonexistent GF10 daily files")
    rows=[]
    for file in sources:
        x=pd.read_parquet(file) if file.suffix.lower()==".parquet" else pd.read_csv(file)
        if not {"grid_id","date"}<=set(x):raise ValueError("Input lacks GF10 date "+str(file))
        x=x.copy();x.grid_id=x.grid_id.astype(str)
        x.date=pd.to_datetime(x.date,errors="raise").dt.normalize()
        if x.duplicated(["grid_id","date"]).any():raise ValueError("Repeated GF10 day within "+str(file))
        rows.append(x)
    # Different source families may have distinct columns; no silent many-to-many.
    result=None
    for part in rows:
        if result is None:
            result=part.set_index(["grid_id","date"])
        else:
            indexed=part.set_index(["grid_id","date"])
            overlapping=set(result.columns)&set(indexed.columns)
            common=result.index.intersection(indexed.index)
            for col in overlapping:
                a=result.loc[common,col];b=indexed.loc[common,col]
                matched=a.notna()&b.notna()
                if matched.any() and not np.allclose(
                    pd.to_numeric(a[matched]),pd.to_numeric(b[matched]),
                    rtol=1e-5,atol=1e-6):
                    raise ValueError("Disagreeing repeated GF10 daily source field "+col)
            result=result.combine_first(indexed)
    result=result.reset_index().sort_values(["grid_id","date"])
    if result.duplicated(["grid_id","date"]).any():
        raise ValueError("Duplicate after source combination")
    out=safe_output(root,"data/derived/"+tag)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    result.to_parquet(out/"fig2_merged_daily_GF10.parquet",index=False)
    qc={"status":"GF10_DAILY_FILES_MERGED_NOT_M03_COMPLETE",
        "n_files":len(sources),"n_rows":len(result),
        "n_grids":result.grid_id.nunique(),
        "n_dates":result.date.nunique(),"n_missing_values":int(result.isna().sum().sum()),
        "all_inputs":[str(x) for x in sources],
        "no_inferred_zero_rain":True,"no_download_or_GEE":True}
    atomic_json(out/"fig2_merged_daily_GF10_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--input-dir",type=Path,required=True)
    p.add_argument("--glob",default="**/fig2_CF_daily_GF10.parquet")
    p.add_argument("--tag",default="fig2_daily_merged_v1")
    a=p.parse_args(argv)
    print(json.dumps(merge(a.root,sorted(a.input_dir.glob(a.glob)),a.tag),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
