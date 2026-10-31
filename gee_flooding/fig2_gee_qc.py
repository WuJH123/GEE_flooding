"""Audit downloaded Fig2 GEE CSVs against an immutable 10km GF10 task manifest.

Never infer success from READY/COMPLETED alone. Strictly check grid membership,
expected columns and rows, numeric and physical ranges, and GHSL totals
against an INDEPENDENT local extraction when a comparison export exists.

Run after download, before fig2_indicators merge. No EE API calls.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd

from .fig2_gee import launch
from .paths import safe_output, atomic_json

FRACTIONS = {"vegetation_fraction","tree_fraction","grass_fraction",
             "cropland_fraction","wetland_fraction","water_fraction",
             "bare_fraction","river_water_fraction","built_fraction_2020",
             "built_nres_fraction_2020","built_neighbor_density","built_fragmentation"}
NONNEG = {"hand_m","slope_deg","upstream_area_km2","elevation_m",
          "population_count_2020","built_area_km2_2020",
          "built_nres_area_km2_2020"}
# Elevation can be negative; do not classify it as nonnegative.
NONNEG.remove("elevation_m")
GROWTH = {"built_growth_2000_2020"}


def _num(col, field):
    v=pd.to_numeric(col,errors="coerce")
    if v.isna().any() or not np.isfinite(v).all():
        raise ValueError(field+" contains null/non-numeric/infinite values")
    if field in FRACTIONS and not v.between(-1e-5,1+1e-5).all():
        raise ValueError(field+" outside [0,1]")
    if field in NONNEG and (v<0).any():
        raise ValueError(field+" has negative values")
    if field in GROWTH and not v.between(-1-1e-5,1+1e-5).all():
        raise ValueError(field+" impossible growth share")
    if field=="population_count_2020" and v.max()>1e8:
        raise ValueError("GF10 population count unusually high; inspect native units")
    if field.endswith("_area_km2_2020") and (v>100.1).any():
        raise ValueError(field+" exceeds physical 100 km2 GF10")
    return v


def validate_one(row, plan, static_dir, exposure_dir):
    grid=plan/row.grid_file
    if not grid.is_file():raise FileNotFoundError("Planned GF10 subset missing "+str(grid))
    expected=pd.read_parquet(grid)
    mode=row["mode"]
    bands=str(row["bands"]).split(",")
    # Reuse the same deterministic identity as the actual export CLI.
    task=launch(grid,0,int(row["n_grid"]),mode,None,
                "GEE_flooding_Figure2",bands=bands)
    name=task["description"]
    directory=static_dir if mode=="static" else exposure_dir
    if directory is None:return dict(job_id=row.job_id,status="CSV_NOT_DOWNLOADED",
                                     export_filename=name+".csv",n_valid=0)
    path=Path(directory)/(name+".csv")
    if not path.is_file():
        return dict(job_id=row.job_id,status="CSV_NOT_DOWNLOADED",
                    export_filename=name+".csv",n_valid=0)
    x=pd.read_csv(path)
    if "grid_id" not in x:raise ValueError("Missing grid_id in "+str(path))
    x.grid_id=x.grid_id.astype(str)
    requested={"grid_id",*bands}
    if requested-set(x.columns):
        raise ValueError("Missing required GEE bands "+str(requested-set(x.columns)))
    if len(x)!=int(row.n_grid) or x.grid_id.duplicated().any():
        raise ValueError("GEE row count/duplicates disagree with task: "+str(path))
    if set(x.grid_id)!=set(expected.grid_id.astype(str)):
        raise ValueError("GEE grid ID mismatch / partial result: "+str(path))
    for b in bands:_num(x[b],b)
    if "urban_fraction_2020" in x:
        ref=expected.set_index("grid_id").urban_fraction_2020.astype(float)
        got=x.set_index("grid_id").urban_fraction_2020.astype(float)
        if (got-ref.reindex(got.index)).abs().gt(1e-5).any():
            raise ValueError("GEE frozen urban_fraction mismatch")
    return dict(job_id=row.job_id,status="CSV_AUDITED_SCHEMA_AND_RANGE",
                export_filename=name+".csv",n_valid=len(x),
                mode=mode,bands=",".join(bands),
                selected_grid_ids="EXACT_MATCH")


def check_independent_built_area(local, exposure_dir):
    """Only a separate BUILT-S GEE shadow export enables independent math QC.

    Not independent physical sensing: the same JRC source is used in both
    pipelines; independent computation and raster projection are compared.
    """
    if local is None or exposure_dir is None:
        return {"status":"NO_SHADOW_REFERENCE"}
    local=pd.read_parquet(local)
    if not {"grid_id","built_area_km2_2020"}<=set(local):
        return {"status":"LOCAL_BUILT_REFERENCE_NOT_AVAILABLE"}
    paths=sorted(Path(exposure_dir).glob("f2_exposure_*.csv"))
    shadow=[]
    for path in paths:
        x=pd.read_csv(path)
        if {"grid_id","built_area_km2_2020"}<=set(x):
            shadow.append(x[["grid_id","built_area_km2_2020"]])
    if not shadow:return {"status":"NO_GEE_BUILT_SHADOW_EXPORT"}
    shadow=pd.concat(shadow,ignore_index=True)
    shadow.grid_id=shadow.grid_id.astype(str)
    if shadow.grid_id.duplicated().any():
        raise ValueError("Duplicate GEE built area shadow reference grid_id")
    local.grid_id=local.grid_id.astype(str)
    j=local[["grid_id","built_area_km2_2020"]].merge(
        shadow,on="grid_id",validate="one_to_one",suffixes=("_local","_gee"))
    if j.empty:return {"status":"NO_OVERLAPPING_SHADOW_GRIDS"}
    a=_num(j.built_area_km2_2020_local,"built_area_km2_2020")
    b=_num(j.built_area_km2_2020_gee,"built_area_km2_2020")
    absolute=(a-b).abs()
    relative=absolute/np.maximum(a,.1)
    # Cross-implementation difference can reflect 100m -> WGS84
    # reprojection; do not silently accept it.
    bad=(absolute>.5)&(relative>.05)
    return dict(status="FAILED_SOURCE_CONSERVATION" if bad.any()
                else "LOCAL_VS_GEE_SOURCE_CROSSCHECK",
                n_overlap=int(len(j)),n_flagged=int(bad.sum()),
                max_abs_km2=float(absolute.max()),
                max_relative_difference=float(relative.max()))


def audit(root,plan_dir,static_dir=None,exposure_dir=None,local=None,
          tag="fig2_gee_postdownload_qc_v1",require_complete=False):
    plan=Path(plan_dir)
    tasks=pd.read_csv(plan/"fig2_gee_backfill_tasks.csv").fillna("")
    required={"job_id","mode","bands","n_grid","grid_file"}
    if required-set(tasks):raise ValueError("Malformed GEE task plan")
    if tasks.job_id.duplicated().any():raise ValueError("Duplicate task IDs")
    records=[]
    for row in tasks.itertuples(index=False):
        try:
            item=validate_one(row,plan,static_dir,exposure_dir)
        except Exception as err:
            item=dict(job_id=row.job_id,status="INVALID_EXPORT",problem=str(err))
        records.append(item)
    errors=[x for x in records if x["status"]=="INVALID_EXPORT"]
    missing=[x for x in records if x["status"]=="CSV_NOT_DOWNLOADED"]
    try:
        shadow=check_independent_built_area(local,exposure_dir)
    except Exception as err:
        shadow=dict(status="INVALID_SHADOW",problem=str(err))
        errors.append(dict(job_id="SOURCE_CONSERVATION",status="INVALID_EXPORT",problem=str(err)))
    if shadow.get("status")=="FAILED_SOURCE_CONSERVATION":
        errors.append(dict(job_id="SOURCE_CONSERVATION",status="INVALID_EXPORT",
                           problem="GEE GHSL source area disagrees with independent local extraction"))
    out=safe_output(root,"reports/"+tag)
    if out.exists():raise FileExistsError(str(out))
    out.mkdir(parents=True,exist_ok=False)
    pd.DataFrame(records).to_csv(out/"fig2_gee_file_audit.csv",index=False)
    report=dict(status="REJECTED" if errors or (require_complete and missing)
                else "PARTIAL" if missing else "ALL_TASK_CSVS_SCHEMA_PASSED",
                n_tasks=len(records),
                n_valid=sum(x["status"]=="CSV_AUDITED_SCHEMA_AND_RANGE" for x in records),
                n_missing=len(missing),n_invalid=len(errors),
                independent_JRC_math_check=shadow,
                dataset_value_validation="ranges and task coverage only; NOT external physical truth",
                publication_ready=False)
    atomic_json(out/"fig2_gee_postdownload_qc.json",report)
    if errors or (require_complete and missing):
        raise ValueError("GEE import failed closed; inspect "+str(out/"fig2_gee_postdownload_qc.json"))
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--gee-static",type=Path)
    p.add_argument("--gee-exposure",type=Path)
    p.add_argument("--local",type=Path,help="Independent JRC GHSL local 2020 GF10 table for shadow QC")
    p.add_argument("--tag",default="fig2_gee_postdownload_qc_v1")
    p.add_argument("--require-complete",action="store_true")
    a=p.parse_args(argv)
    print(json.dumps(audit(a.root,a.plan,a.gee_static,a.gee_exposure,
                           a.local,a.tag,a.require_complete),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
