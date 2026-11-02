"""Figure 2 M04: audited LOCAL-ONLY frozen GF10 static reference table.

Combines an existing QA'd GHSL182/fig2_indicators table with multiple,
disjoint/versioned local native-raster extraction batches. No GEE calls,
downloads, annual/daily weather columns or invented zero fills.

Every source needs its sibling QC JSON. The time contract is immutable:
terrain=static, GHSL2000/2020=historical/frozen, WorldCover=2021 snapshot,
not a different 2021-25 land-cover measurement for each event year.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from .fig2_indicators import CORE, EXPOSURE, CONTEXT, FRACTIONS, NONNEG
from .fig2_local_exact import SUPPORTED as LOCAL_SEMANTICS
from .fig2_resilience import catalog
from .paths import safe_output, atomic_json

STATIC_EPOCH = {
    "hand_m":"static", "slope_deg":"static", "elevation_m":"static",
    "upstream_area_km2":"static", "river_water_fraction":"static",
    "urban_fraction_2020":"2020", "built_fraction_2000":"2000",
    "built_fraction_2020":"2020", "built_area_km2_2020":"2020",
    "built_nres_fraction_2020":"2020", "built_nres_area_km2_2020":"2020",
    "population_count_2020":"2020",
    "built_neighbor_density":"2020","built_fragmentation":"2020",
    "built_growth_2000_2020":"2000-2020",
    "vegetation_fraction":"2021","tree_fraction":"2021",
    "grass_fraction":"2021","cropland_fraction":"2021",
    "wetland_fraction":"2021","water_fraction":"2021","bare_fraction":"2021",
    "impervious_fraction":"2020", "built_volume_m3":"2020",
}
# Core is the frozen manuscript M0-M4 terrain/surface/form/growth input;
# a separate GHSL population/area group is a useful Figure4/5 bridge.
REQUIRED = CORE | EXPOSURE | {"urban_fraction_2020"}
MODEL_REFERENCE = "frozen_surface_2020_2021"
PROHIBITED_WORDS = {"rain_", "api_", "observed_news", "flood_observed",
                    "soil_water_", "temperature_", "reporting_propensity"}


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            part=f.read(1024*1024)
            if not part:break
            h.update(part)
    return h.hexdigest()


def _read_source(path,kind,n_expected):
    path=Path(path)
    if not path.is_file() or path.suffix.lower()!=".parquet":
        raise FileNotFoundError("Require existing audited GF10 parquet: "+str(path))
    qc_path=path.parent/("fig2_GF10_indicator_merge_qc.json" if kind=="baseline"
                         else "fig2_local_exact_qc.json")
    if not qc_path.is_file():
        raise ValueError("Missing sibling source QA manifest: "+str(qc_path))
    audit=json.loads(qc_path.read_text(encoding="utf-8"))
    if kind=="baseline":
        if int(audit.get("frozen_grid_count",-1))!=n_expected:
            raise ValueError("Baseline frozen GF10 scope mismatch")
        if int(audit.get("n_conflicts",-1))!=0:
            raise ValueError("Unresolved conflicts in previous GHSL/GF10 baseline")
        if audit.get("status") not in (
            "PILOT_REQUIRES_REVIEW",
            "GF10_INDICATOR_SCOPE_COMPLETE_NEEDS_EXTERNAL_VALIDATION"):
            raise ValueError("Previous baseline merge was not an audited product")
    else:
        if audit.get("grid_crs")!="EPSG:6933":
            raise ValueError("Local extraction GF10 CRS not frozen EPSG:6933")
        if audit.get("method") not in (
            "exactextract_native_pixel_fraction_weighted",
            "shapely_native_pixel_fraction_weighted"):
            raise ValueError("Unverified local extraction backend")
        if not .5<=float(audit.get("min_pixel_coverage",0))<=1:
            raise ValueError("Invalid local extraction coverage contract")
    df=pd.read_parquet(path)
    illegal={"date","date_utc","year","storm_id","event_id",
             "observed_news_onset","reporting_propensity"}
    illegal.update(k for k in df.columns if any(str(k).startswith(prefix)
                   for prefix in PROHIBITED_WORDS))
    forbidden=illegal.intersection(df.columns)
    if forbidden:
        raise ValueError("Daily/annual/event fields belong outside frozen static GF10: "+str(sorted(forbidden)))
    if "grid_id" not in df:raise ValueError("Local source missing original GF10 IDs")
    df=df.copy();df.grid_id=df.grid_id.astype(str)
    if df.grid_id.duplicated().any():raise ValueError("Duplicated GF10 cell in "+str(path))
    if kind=="local" and audit.get("grid_cell_count")!=len(df):
        raise ValueError("Local source QA row count differs from parquet")
    fields=[key for key in df.columns if key in STATIC_EPOCH and key!="urban_fraction_2020"]
    if not fields:raise ValueError("No recognized static/epoch fields in "+str(path))
    if kind=="local":
        coverage=audit.get("indicator_coverage",{})
        raster_meta=audit.get("raster_metadata",[])
        for key in fields:
            if key not in coverage:
                raise ValueError("Local source did not QA indicator "+key)
            if key not in LOCAL_SEMANTICS:
                raise ValueError("Local source field unsupported by local raster engine: "+key)
            matches=[v for v in raster_meta if v.get("name")==key]
            if not matches or any(str(v.get("data_year"))!=STATIC_EPOCH[key] for v in matches):
                raise ValueError("Local native source has incompatible epoch for "+key)
            if any(v.get("data_source")!=LOCAL_SEMANTICS[key][1] for v in matches):
                raise ValueError("Local native data family does not match metric for "+key)
            cov_key="coverage_"+key
            if cov_key not in df:raise ValueError("Local source lacks per-cell pixel coverage "+key)
            cov=pd.to_numeric(df[cov_key],errors="coerce")
            if cov.isna().any() or not cov.between(0,1.000001).all():
                raise ValueError("Invalid local source coverage_"+key)
            # Source's own native pixel minimum coverage is retained.
            insufficient=cov.lt(float(audit["min_pixel_coverage"])-1e-8)
            if (df[key].notna()&insufficient).any():
                raise ValueError("Local indicator marked nonnull despite insufficient native coverage")
            if int(df[key].notna().sum())!=int(coverage[key].get("valid_n",-1)):
                raise ValueError("Local indicator n_valid disagrees with source QC "+key)
    return path,qc_path,df,fields,audit


def _number(series,name):
    x=pd.to_numeric(series,errors="coerce")
    if x.notna().any() and not np.isfinite(x.dropna().to_numpy(float)).all():
        raise ValueError("NaN/inf native static field "+name)
    observed=x.dropna()
    if name in FRACTIONS and not observed.between(-1e-5,1.00001).all():
        raise ValueError("Static fraction outside [0,1]: "+name)
    if name=="built_growth_2000_2020" and not observed.between(-1,1).all():
        raise ValueError("Historic built growth must be [-1,1]")
    if name in NONNEG and (observed<0).any():
        raise ValueError("Negative exposure/terrain "+name)
    if name=="slope_deg" and (observed>90).any():
        raise ValueError("Slope in degrees exceeds 90")
    if name.endswith("_area_km2_2020") and (observed>100.1).any():
        raise ValueError("2020 GF10 area exceeds 100km²: "+name)
    return x.astype(float)


def _check_relationships(x):
    # All checks only where both values are available, never implicit zero.
    comparisons=[
        ("built_area_km2_2020","built_fraction_2020", lambda a,b: abs(a/100-b),.005),
        ("built_nres_area_km2_2020","built_nres_fraction_2020",
            lambda a,b: abs(a/100-b),.005),
        ("built_fraction_2000","built_fraction_2020",
            lambda a,b: b-a, None),
    ]
    for left,right,f,tolerance in comparisons[:2]:
        if {left,right}<=set(x):
            valid=x[left].notna()&x[right].notna()
            if (f(x.loc[valid,left],x.loc[valid,right])>tolerance).any():
                raise ValueError("Inconsistent native GHSL area vs GF10 fraction: "+left)
    if {"built_nres_area_km2_2020","built_area_km2_2020"}<=set(x):
        subset=x[["built_nres_area_km2_2020","built_area_km2_2020"]].dropna()
        if (subset.iloc[:,0]>subset.iloc[:,1]+.01).any():
            raise ValueError("GHS NRES area exceeds total built area")
    if {"built_fraction_2000","built_fraction_2020","built_growth_2000_2020"}<=set(x):
        z=x[["built_fraction_2000","built_fraction_2020",
             "built_growth_2000_2020"]].dropna()
        if ((z.built_fraction_2020-z.built_fraction_2000-
             z.built_growth_2000_2020).abs()>.03).any():
            raise ValueError("Historical growth not equal to the two native epoch fractions")
    if {"tree_fraction","grass_fraction","cropland_fraction",
        "wetland_fraction","vegetation_fraction"}<=set(x):
        subset=x[["tree_fraction","grass_fraction","cropland_fraction",
                  "wetland_fraction","vegetation_fraction"]].dropna()
        if (subset[["tree_fraction","grass_fraction",
                    "cropland_fraction","wetland_fraction"]].sum(axis=1)>
                    subset.vegetation_fraction+.025).any():
            raise ValueError("WorldCover disjoint vegetation classes exceed union")


def assemble(root,grid,tag,baseline=None,locals=None,
             conflict_fraction=.03,conflict_relative=.10):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use new immutable fig2_* output tag")
    if not 0<=conflict_fraction<=.03 or not 0<=conflict_relative<=.10:
        raise ValueError("Conflicts cannot be hidden by increasing tolerances")
    grid=Path(grid)
    gf=pd.read_parquet(grid)
    needs={"grid_id","grid_x","grid_y","urban_fraction_2020"}
    if needs-set(gf):raise ValueError("Not the frozen GF10 grid contract")
    gf=gf.copy();gf.grid_id=gf.grid_id.astype(str)
    if gf.grid_id.duplicated().any():raise ValueError("Duplicate frozen GF10 IDs")
    if not np.all(pd.to_numeric(gf.urban_fraction_2020,errors="coerce").between(0,1)):
        raise ValueError("Missing/invalid frozen 2020 urban fraction")
    if any(str(gid)!=f"{int(x)}_{int(y)}"
           for gid,x,y in zip(gf.grid_id,gf.grid_x,gf.grid_y)):
        raise ValueError("GF10 identifier not consistent with original EPSG6933 origin")
    if not baseline and not locals:
        raise ValueError("Need audited local sources; cannot generate zeros")
    inputs=([("baseline",baseline)] if baseline else [])+[
        ("local",p) for p in (locals or [])]
    if len(inputs)>100:raise ValueError("Split local extract files into batches")
    seen_files=set()
    out=gf[["grid_id","urban_fraction_2020"]].set_index("grid_id")
    trusted=out.index
    provenance={k:pd.Series("NOT_OBSERVED",index=trusted,dtype="object")
                for k in STATIC_EPOCH if k!="urban_fraction_2020"}
    disagreements=[]
    inputs_provenance=[]
    for kind,p in inputs:
        path,qc,df,cols,audit=_read_source(p,kind,len(gf))
        if str(path.resolve()) in seen_files:
            raise ValueError("Same native local file reused twice")
        seen_files.add(str(path.resolve()))
        unknown=set(df.grid_id)-set(trusted)
        if unknown:raise ValueError("Source contains out-of-scope/non-frozen GF10 IDs")
        df=df.set_index("grid_id")
        for key in cols:
            values=_number(df[key],key).reindex(trusted)
            # Existing frozen GHSL value is authoritative when conflict-free.
            previous=out[key] if key in out else pd.Series(np.nan,index=trusted)
            both=previous.notna()&values.notna()
            if both.any():
                difference=(previous[both]-values[both]).abs()
                if key in FRACTIONS or key=="built_growth_2000_2020":
                    invalid=difference>conflict_fraction
                else:
                    scale=np.maximum(previous[both].abs(),values[both].abs())
                    invalid=difference>np.maximum(1e-4,conflict_relative*scale)
                for gid in difference.index[invalid]:
                    disagreements.append(dict(grid_id=gid,indicator=key,
                        older=float(previous[gid]),newer=float(values[gid]),
                        older_source=str(provenance[key][gid]),newer_source=str(path),
                        difference=float(difference[gid])))
            fill=previous.isna()&values.notna()
            if key not in out:out[key]=previous
            out.loc[fill,key]=values[fill]
            provenance[key].loc[fill]=str(path)
        inputs_provenance.append(dict(
            type=kind,path=str(path),sha256=_sha(path),
            qc_path=str(qc),qc_sha256=_sha(qc),
            fields=cols,qa_method=audit.get("method","audited_baseline")))
    if disagreements:
        raise ValueError(f"{len(disagreements)} local source conflicts: "
                         "do not select source by convenience; resolve source versions first. "
                         +str(disagreements[:3]))
    if "built_fraction_2020" in out and "built_fraction_2000" in out:
        derived=out.built_fraction_2020-out.built_fraction_2000
        if "built_growth_2000_2020" in out:
            already=out.built_growth_2000_2020
            inconsistent=already.notna()&derived.notna()&(already-derived).abs().gt(.03)
            if inconsistent.any():raise ValueError("Historical growth invariant conflict")
            fill=already.isna()&derived.notna()
            out.loc[fill,"built_growth_2000_2020"]=derived[fill]
        else:
            fill=derived.notna()
            out["built_growth_2000_2020"]=derived
        provenance["built_growth_2000_2020"].loc[fill]="DERIVED_FROM_2000_AND_2020"
    # Nonchanging frozen auxiliary indicators are NOT inferred or extrapolated by event date.
    _check_relationships(out)
    for col in list(out.columns):
        if col!="urban_fraction_2020" and col not in STATIC_EPOCH:
            raise ValueError("Unexpected temporal field in frozen static output "+col)
    # Attach per-indicator provenance; keep full-year raw observations in their OWN table.
    for key in sorted(STATIC_EPOCH):
        if key in out and key!="urban_fraction_2020":
            out[key+"_source"]=provenance[key].where(out[key].notna(),"NOT_OBSERVED")
    out=out.reset_index()
    out["urban_fraction_2020_source"]="FROZEN_GF10_2020_SMOD"
    fieldrows=[]
    cat=catalog().set_index("name")
    for key,epoch in STATIC_EPOCH.items():
        if key not in out:
            valid=0;observed=pd.Series([],dtype=float)
        else:
            valid=int(out[key].notna().sum())
            observed=out[key].dropna()
        fieldrows.append(dict(indicator=key,temporal_type=("static" if epoch=="static"
            else "historical_change" if epoch=="2000-2020" else "epoch_snapshot"),
            source_epoch=epoch,model_role=(
                "M0-M4_required" if key in REQUIRED else
                "historical_baseline" if key in CONTEXT else "optional_or_context"),
            unit=str(cat.loc[key,"unit"]) if key in cat.index else "unknown",
            n_valid=valid,n_missing=len(gf)-valid,
            coverage_fraction=valid/len(gf),
            annual_update_from_static=False,
            note=("WorldCover 2021 is a fixed retrospective snapshot, not 2021-25 yearly state"
                  if epoch=="2021" else
                  "GHSL multi-year interpolated/extrapolated reference, not a measured daily state"
                  if epoch in ("2000","2020","2000-2020") else
                  "Stable terrain proxy, not time-invariant physical drainage infrastructure")))
    fieldtable=pd.DataFrame(fieldrows)
    coverage={}
    for key in REQUIRED:
        coverage[key]=int(out[key].notna().sum()) if key in out else 0
    missing_by_cell=[]
    for row in out.itertuples(index=False):
        miss=[key for key in sorted(REQUIRED) if key not in out or pd.isna(getattr(row,key,np.nan))]
        missing_by_cell.append(dict(grid_id=row.grid_id,
                                    missing_required_count=len(miss),
                                    missing_required_indicators=";".join(miss)))
    gaps=pd.DataFrame(missing_by_cell)
    _count=int((gaps.missing_required_count>0).sum())
    outdir=safe_output(root,"data/derived/"+tag)
    if outdir.exists():raise FileExistsError("Refusing to overwrite version "+str(outdir))
    outdir.mkdir(parents=True,exist_ok=False)
    out.to_parquet(outdir/"fig2_GF10_local_static_wide.parquet",index=False)
    fieldtable.to_csv(outdir/"fig2_static_indicator_dictionary.csv",index=False,encoding="utf-8-sig")
    gaps.to_parquet(outdir/"fig2_GF10_required_missing_by_grid.parquet",index=False)
    fieldtable.loc[fieldtable.n_missing.gt(0)].to_csv(
        outdir/"fig2_indicator_missingness.csv",index=False,encoding="utf-8-sig")
    qc=dict(status=("LOCAL_STATIC_PILOT_COMPLETE_NOT_GLOBALLY_VALIDATED" if _count==0
                    else "LOCAL_STATIC_PARTIAL_NEEDS_BACKFILL"),
        frozen_grid_count=len(gf),n_grids_missing_at_least_one_required=_count,
        required_field_count=len(REQUIRED),
        required_valid_count=coverage,
        local_sources=[p["path"] for p in inputs_provenance],
        input_fingerprints=inputs_provenance,
        frozen_GF10_path=str(grid),frozen_GF10_sha256=_sha(grid),
        source_epoch_reference=MODEL_REFERENCE,
        chronology="static+2000/2020 historic + fixed 2021 snapshot; join daily observations later by grid_id only",
        future_annual_data_joined=False,daily_weather_joined=False,
        report_outcome_joined=False,
        zero_filled_missing=False,GEE_jobs_submitted=0,download_jobs=0,
        conflicts=0,n_conflicts=0,global_scope_complete=False,
        publication_ready=False)
    atomic_json(outdir/"fig2_local_static_qc.json",qc)
    # Compatibility is still NOT the old fig2_indicators GF10 QC gate;
    # model preparation must explicitly accept this new audited format.
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--baseline",type=Path,
                   help="Earlier audited fig2_indicators merged GHSL2020 table")
    p.add_argument("--local",type=Path,action="append",default=[],
                   help="Repeat once for EACH fig2_local_exact audited Parquet batch")
    p.add_argument("--tag",default="fig2_local_static_v1")
    a=p.parse_args(argv)
    print(json.dumps(assemble(a.root,a.grid,a.tag,a.baseline,a.local),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
