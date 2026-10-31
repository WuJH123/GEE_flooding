"""Reconcile locally extracted and GEE-exported indicators on frozen GF10.

Local-first means prefer a successfully QC'd native-raster extraction; when
local coverage is partial, fill with completed GEE per-cell table exports.
Never silently prefer two inconsistent estimates: flag each disagreement
and keep all provenance/coverage. Missing values remain NaN, not zero.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .fig2_resilience import catalog
from .paths import safe_output,atomic_json

CORE={"hand_m","slope_deg","upstream_area_km2",
      "vegetation_fraction","built_fraction_2020",
      "built_neighbor_density","built_fragmentation","built_growth_2000_2020"}
EXPOSURE={"population_count_2020","built_area_km2_2020",
          "built_nres_area_km2_2020"}
CONTEXT={"built_fraction_2000"}
VALID=set(catalog().name)|CONTEXT
FRACTIONS={name for name in VALID if name.endswith("_fraction")
           or name in {"built_neighbor_density","built_fragmentation"}}
NONNEG={"hand_m","upstream_area_km2","population_count_2020",
        "built_area_km2_2020","built_nres_area_km2_2020",
        "built_volume_m3","slope_deg"}


def source_frame(data,domain,name,allow_partial=True):
    if "grid_id" not in data:
        raise ValueError(name+": missing GF10 id")
    df=data.copy()
    df["grid_id"]=df.grid_id.astype(str)
    if df.grid_id.duplicated().any():
        raise ValueError(name+": duplicate grid_id in exported/local batch")
    unknown=set(df.grid_id)-set(domain)
    if unknown and not allow_partial:
        raise ValueError(name+": unexpected GF10 IDs")
    df=df.loc[df.grid_id.isin(domain)]
    columns=[k for k in df if k in VALID and k!="urban_fraction_2020"]
    if not columns:
        raise ValueError(name+": no recognized Figure2 indicators")
    for col in columns:
        df[col]=pd.to_numeric(df[col],errors="coerce")
        finite=df[col].dropna()
        if not np.isfinite(finite).all():
            raise ValueError(name+": nonfinite "+col)
        if col in FRACTIONS and not finite.between(-1e-5,1.00001).all():
            raise ValueError(name+": invalid physical fraction "+col)
        if col in NONNEG and (finite<0).any():
            raise ValueError(name+": negative "+col)
    return df[["grid_id"]+columns].set_index("grid_id")


def _load_gee(directory,prefix):
    if not directory:return None
    directory=Path(directory)
    if not directory.is_dir():raise FileNotFoundError(str(directory))
    files=sorted(directory.glob(prefix+"*.csv"))
    if not files:
        raise FileNotFoundError(str(directory)+": no "+prefix+" CSV")
    return pd.concat([pd.read_csv(p) for p in files],ignore_index=True)


def assemble(root,grid,tag,local=None,gee_static=None,gee_exposure=None,
             conflict_fraction=.03,conflict_relative=.10):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Provide immutable fig2_* output version")
    from .fig2_local_exact import selected_grid
    frozen=pd.read_parquet(grid)
    if not {"grid_id","urban_fraction_2020"}<=set(frozen):
        raise ValueError("Frozen GF10 must have urban_fraction_2020")
    frozen["grid_id"]=frozen.grid_id.astype(str)
    if frozen.grid_id.duplicated().any():raise ValueError("Frozen grid duplicate IDs")
    if frozen.urban_fraction_2020.isna().any():
        raise ValueError("Frozen city domain has missing urban fraction")
    if not frozen.urban_fraction_2020.between(0,1).all():
        raise ValueError("Invalid frozen urban fraction")
    domain=frozen.grid_id.tolist()
    out=frozen[["grid_id","urban_fraction_2020"]].copy().set_index("grid_id")
    sources=[]
    if local:
        local=Path(local)
        audit=local.parent/"fig2_local_exact_qc.json"
        if not audit.is_file():
            raise ValueError("Only audited fig2_local_exact outputs can enter local-first merge")
        metadata=json.loads(audit.read_text(encoding="utf-8"))
        if metadata.get("method")!="exactextract_native_pixel_fraction_weighted":
            raise ValueError("Local exactextract provenance contract missing")
        sources.append(("LOCAL_EXACT",source_frame(pd.read_parquet(local),domain,"LOCAL_EXACT")))
    if gee_static:
        sources.append(("GEE_STATIC",source_frame(
            _load_gee(gee_static,"f2_static_"),domain,"GEE_STATIC")))
    if gee_exposure:
        sources.append(("GEE_EXPOSURE",source_frame(
            _load_gee(gee_exposure,"f2_exposure_"),domain,"GEE_EXPOSURE")))
    if not sources:raise ValueError("Require at least one audited local or completed GEE input")
    fields=sorted(set().union(*(set(x.columns) for _,x in sources)))
    coverage=[]
    conflicts=[]
    for field in fields:
        if field.startswith("coverage_"):continue
        chosen=pd.Series(np.nan,index=out.index,dtype="float64")
        provenance=pd.Series("NOT_OBSERVED",index=out.index,dtype="object")
        first_values=None
        first_source=None
        for source_name,df in sources:
            if field not in df:continue
            incoming=df[field].reindex(out.index).astype(float)
            overlap=chosen.notna() & incoming.notna()
            if overlap.any():
                absdiff=(chosen.loc[overlap]-incoming.loc[overlap]).abs()
                if field in FRACTIONS:
                    threshold=conflict_fraction
                else:
                    threshold=np.maximum(1e-4, conflict_relative*np.maximum(
                        chosen.loc[overlap].abs(),incoming.loc[overlap].abs()))
                problematic=absdiff>threshold
                for grid_id in absdiff.index[problematic]:
                    conflicts.append(dict(grid_id=grid_id,indicator=field,
                                          kept_source=provenance[grid_id],
                                          alternate_source=source_name,
                                          kept_value=float(chosen[grid_id]),
                                          alternate_value=float(incoming[grid_id]),
                                          abs_difference=float(absdiff.loc[grid_id])))
            fill=chosen.isna() & incoming.notna()
            chosen.loc[fill]=incoming.loc[fill]
            provenance.loc[fill]=source_name
        out[field]=chosen
        out[field+"_source"]=provenance
        coverage.append(dict(name=field,n_valid=int(chosen.notna().sum()),
                             n_missing=int(chosen.isna().sum()),
                             coverage_ratio=float(chosen.notna().mean()),
                             source_priority="LOCAL_EXACT > GEE_STATIC > GEE_EXPOSURE"))
    if {"built_fraction_2000","built_fraction_2020"}<=set(out):
        growth=(out.built_fraction_2020-out.built_fraction_2000)
        if "built_growth_2000_2020" in out:
            existing=out.built_growth_2000_2020
            disagree=(growth-existing).abs().gt(conflict_fraction) & growth.notna() & existing.notna()
            for key in out.index[disagree]:
                conflicts.append(dict(grid_id=key,indicator="built_growth_2000_2020",
                         kept_source=out.loc[key,"built_growth_2000_2020_source"],
                         alternate_source="DERIVED_LOCAL_2000_2020",
                         kept_value=float(existing.loc[key]),
                         alternate_value=float(growth.loc[key]),
                         abs_difference=float(abs(growth.loc[key]-existing.loc[key]))))
            fill=existing.isna() & growth.notna()
            out.loc[fill,"built_growth_2000_2020"]=growth.loc[fill]
            out.loc[fill,"built_growth_2000_2020_source"]="DERIVED_LOCAL_2000_2020"
        else:
            out["built_growth_2000_2020"]=growth
            out["built_growth_2000_2020_source"]=np.where(
              growth.notna(),"DERIVED_LOCAL_2000_2020","NOT_OBSERVED")
        coverage=[x for x in coverage if x["name"]!="built_growth_2000_2020"]
        field="built_growth_2000_2020"
        coverage.append(dict(name=field,n_valid=int(out[field].notna().sum()),
             n_missing=int(out[field].isna().sum()),
             coverage_ratio=float(out[field].notna().mean()),
             source_priority="LOCAL_EXACT > GEE_STATIC > GEE_EXPOSURE > DERIVED"))
    out=out.reset_index()
    gaps=[]
    rows=[]
    for name in sorted(CORE|EXPOSURE|{"urban_fraction_2020"}):
        if name=="urban_fraction_2020":
            nvalid=len(out)
            needed=0
        else:
            nvalid=int(out[name].notna().sum()) if name in out else 0
            needed=len(out)-nvalid
        rows.append(dict(indicator=name,n_valid=nvalid,n_missing=needed,
                         complete=bool(needed==0)))
        if needed:
            gaps.append(dict(indicator=name,missing_GF10_cells=needed,
                       action="GEE_FILL_MISSING_CELLS_ONLY_OR_AUDIT_NEW_LOCAL_TILES",
                       note="No zero-fill; finite values still require native source provenance"))
    outdir=safe_output(root,"data/derived/"+tag)
    if outdir.exists():raise FileExistsError("Refusing to overwrite "+str(outdir))
    outdir.mkdir(parents=True,exist_ok=False)
    out.to_parquet(outdir/"fig2_GF10_resilience_indicators.parquet",index=False)
    pd.DataFrame(coverage).to_csv(outdir/"fig2_indicator_coverage.csv",index=False)
    pd.DataFrame(rows).to_csv(outdir/"fig2_core_indicator_gate.csv",index=False)
    pd.DataFrame(gaps,columns=["indicator","missing_GF10_cells","action","note"]).to_csv(
        outdir/"fig2_gee_missing_indicator_plan.csv",index=False)
    pd.DataFrame(conflicts,columns=["grid_id","indicator","kept_source",
        "alternate_source","kept_value","alternate_value","abs_difference"]).to_csv(
        outdir/"fig2_source_conflicts.csv",index=False)
    qc={"status":"PILOT_REQUIRES_REVIEW" if gaps or conflicts
                else "GF10_INDICATOR_SCOPE_COMPLETE_NEEDS_EXTERNAL_VALIDATION",
        "frozen_grid_count":len(out),"source_files":[s for s,_ in sources],
        "local_preferred":True,"n_conflicts":len(conflicts),"n_missing_core_indicators":len(gaps),
        "no_zero_filled_missing_values":True,"gee_tasks_submitted":0,
        "global_coverage_validated":False,"real_pluvial_validation":False,
        "publication_ready":False}
    atomic_json(outdir/"fig2_GF10_indicator_merge_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--local",type=Path,default=None,help="Audited output of fig2_local_exact")
    p.add_argument("--gee-static",type=Path,default=None)
    p.add_argument("--gee-exposure",type=Path,default=None)
    p.add_argument("--tag",default="fig2_integrated_GF10_v1")
    a=p.parse_args(argv)
    print(json.dumps(assemble(a.root,a.grid,a.tag,a.local,
                              a.gee_static,a.gee_exposure),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
