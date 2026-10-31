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
             "built_fraction_2000",
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
    mode=row.mode
    bands=str(row.bands).split(",")
    # Reuse the same deterministic identity as the actual export CLI.
    task=launch(grid,0,int(row.n_grid),mode,None,
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


def check_nres_never_exceeds_total(local, exposure_dir):
    """2020 GHSL nonresidential built area cannot exceed total built area."""
    if local is None or exposure_dir is None:
        return {"status":"NO_NRES_COMPARISON"}
    ref=pd.read_parquet(local)
    if not {"grid_id","built_area_km2_2020"}<=set(ref):
        return {"status":"NO_LOCAL_BUILT_TOTAL"}
    chunks=[]
    for path in sorted(Path(exposure_dir).glob("f2_exposure_*.csv")):
        data=pd.read_csv(path)
        if {"grid_id","built_nres_area_km2_2020"}<=set(data):
            chunks.append(data[["grid_id","built_nres_area_km2_2020"]])
    if not chunks:return {"status":"NO_NRES_EXPORTED"}
    nres=pd.concat(chunks,ignore_index=True)
    nres.grid_id=nres.grid_id.astype(str)
    if nres.grid_id.duplicated().any():
        raise ValueError("Duplicate GEE nres area rows across exports")
    ref.grid_id=ref.grid_id.astype(str)
    matched=ref[["grid_id","built_area_km2_2020"]].merge(
        nres,on="grid_id",validate="one_to_one")
    if matched.empty:return {"status":"NO_SHARED_NRES_GF10"}
    total=_num(matched.built_area_km2_2020,"built_area_km2_2020")
    part=_num(matched.built_nres_area_km2_2020,"built_nres_area_km2_2020")
    violation=part>total+.5
    return dict(status="FAILED_NRES_SUBSET_TOTAL" if violation.any()
                else "NRES_SUBSET_CHECK",n_overlap=int(len(matched)),
                n_violations=int(violation.sum()),
                maximum_excess_km2=float((part-total).max()),
                allowable_reprojection_tolerance_km2=.5)


def check_ghsl_growth_identity(local, static_dir):
    """Check separately exported GEE historical share and growth against
    locally measured 2020 built share (same JRC lineage, two pipelines).
    """
    if local is None or static_dir is None:
        return {"status":"NO_HISTORICAL_SOURCE_CHECK"}
    original=pd.read_parquet(local)
    if not {"grid_id","built_fraction_2020"}<=set(original):
        return {"status":"NO_LOCAL_2020_BASELINE"}
    frames=[]
    for path in sorted(Path(static_dir).glob("f2_static_*.csv")):
        x=pd.read_csv(path)
        req={"grid_id","built_fraction_2000","built_growth_2000_2020"}
        if req.issubset(x):
            frames.append(x[list(req)].copy())
    if not frames:return {"status":"NO_GEE_2000_AND_GROWTH_CROSSCHECK"}
    history=pd.concat(frames,ignore_index=True)
    history.grid_id=history.grid_id.astype(str)
    if history.grid_id.duplicated().any():
        raise ValueError("Repeated historical growth/2000 GEE grid_id")
    original.grid_id=original.grid_id.astype(str)
    joined=original[["grid_id","built_fraction_2020"]].merge(
        history,on="grid_id",validate="one_to_one")
    if joined.empty:return {"status":"NO_OVERLAPPING_HISTORICAL_GRIDS"}
    b00=_num(joined.built_fraction_2000,"built_fraction_2000")
    grow=_num(joined.built_growth_2000_2020,"built_growth_2000_2020")
    b20=_num(joined.built_fraction_2020,"built_fraction_2020")
    delta=(b00+grow-b20).abs()
    bad=delta>.03
    return dict(status="FAILED_HISTORICAL_SHARE_IDENTITY" if bad.any()
                else "HISTORICAL_SHARE_CROSSCHECK",
                n_overlap=int(len(joined)),
                n_flagged=int(bad.sum()),
                max_fraction_difference=float(delta.max()),
                tolerance_fraction=.03)


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
    try:
        nres=check_nres_never_exceeds_total(local,exposure_dir)
    except Exception as err:
        nres=dict(status="INVALID_NRES_CHECK",problem=str(err))
        errors.append(dict(job_id="NRES_SUBSET",status="INVALID_EXPORT",problem=str(err)))
    if nres.get("status")=="FAILED_NRES_SUBSET_TOTAL":
        errors.append(dict(job_id="NRES_SUBSET",status="INVALID_EXPORT",
                           problem="Nonresidential GHSL area exceeds total built area"))
    try:
        growth=check_ghsl_growth_identity(local,static_dir)
    except Exception as err:
        growth=dict(status="INVALID_HISTORICAL_QC",problem=str(err))
        errors.append(dict(job_id="HISTORICAL_GROWTH",status="INVALID_EXPORT",problem=str(err)))
    if growth.get("status")=="FAILED_HISTORICAL_SHARE_IDENTITY":
        errors.append(dict(job_id="HISTORICAL_GROWTH",status="INVALID_EXPORT",
                           problem="GEE GHSL 2000 plus growth differs from local 2020 beyond tolerance"))
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
                nonresidential_subset_check=nres,
                historical_GHSL_2000_2020_identity_check=growth,
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
