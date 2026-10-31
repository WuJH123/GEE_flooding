"""Make a frozen GF10 study subset containing only cells missing one indicator.

No Earth Engine task starts here. Never recalculate the 10km geometry or
change grid_id; output can be passed to fig2_gee --bands indicator.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
from .paths import safe_output,atomic_json
from .fig2_gee import GEE_STATIC,EXPOSURE


def make(root,frozen,integrated,indicator,tag):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use new versioned fig2_* tag")
    if indicator not in set(GEE_STATIC)|set(EXPOSURE):
        raise ValueError("Only GEE static/exposure indicator may select a gap-grid")
    domain=pd.read_parquet(frozen)
    if domain.grid_id.duplicated().any():raise ValueError("Frozen grid ID duplicated")
    current=pd.read_parquet(integrated)
    if current.grid_id.duplicated().any():raise ValueError("Merged indicators contain duplicate grid")
    if indicator not in current:
        missing=set(domain.grid_id.astype(str))
    else:
        available=current.loc[current[indicator].notna(),"grid_id"].astype(str)
        missing=set(domain.grid_id.astype(str))-set(available)
    sub=domain.loc[domain.grid_id.astype(str).isin(missing)].copy()
    if len(sub)==0:
        raise ValueError("No missing "+indicator+" in declared frozen subset")
    out=safe_output(root,"data/reference/"+tag)
    if out.exists():raise FileExistsError(str(out))
    out.mkdir(parents=True,exist_ok=False)
    sub.sort_values("grid_id").to_parquet(out/"fig2_GF10_missing_grid.parquet",index=False)
    qc=dict(status="GEE_GAP_GRID_DRY_PLAN_ONLY",indicator=indicator,
            missing_GF10_count=int(len(sub)),
            original_frozen_GF10_count=len(domain),
            grid_crs="EPSG:6933",same_grid_ids_and_coordinates=True,
            gee_tasks_submitted=0)
    atomic_json(out/"fig2_gap_grid_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--indicators",type=Path,required=True)
    p.add_argument("--indicator",required=True)
    p.add_argument("--tag",default="fig2_gap_hand_v1")
    a=p.parse_args(argv)
    print(json.dumps(make(a.root,a.grid,a.indicators,a.indicator,a.tag),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
