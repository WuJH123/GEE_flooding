"""Freeze an unbiased GF10 subset for bounded Figure 2 GEE exports.

Selects by UCDB geographic strata; never by Groundsource positive frequency.
The output is still the original EPSG:6933 10km cells and IDs, NOT a regrid.
All writes are versioned under E:/GEE_flooding; old project is read-only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from .paths import safe_output,atomic_json
from .fig2_gee import wgs84_ring


def rank(value,seed):
    return hashlib.sha256((str(seed)+"|"+str(value)).encode()).hexdigest()


def sample(grid,crosswalk,city_meta,max_cities=40,cells_per_city=12,seed=42,frozen_v3=None):
    if not 5<=max_cities<=500 or not 1<=cells_per_city<=100:
        raise ValueError("Restrict city count (5-500) and cells per city (1-100)")
    grid=pd.read_parquet(grid)
    x=pd.read_parquet(crosswalk,columns=["grid_id","city_id"])
    c=pd.read_csv(city_meta)
    req=["city_id","continent","koppen_broad"]
    if any(k not in c for k in req):
        raise ValueError("Figure 1 v2 UCDB city metadata missing continent/koppen stratum")
    if grid.grid_id.duplicated().any() or x.grid_id.duplicated().any() or c.city_id.duplicated().any():
        raise ValueError("Duplicate ID in GF10 or UCDB records")
    for frame in [grid,x,c]:
        if "grid_id" in frame:frame["grid_id"]=frame.grid_id.astype(str)
        if "city_id" in frame:frame["city_id"]=frame.city_id.astype(str)
    linked=x.merge(c[req],on="city_id",how="inner",validate="many_to_one")
    linked=linked.merge(grid,on="grid_id",how="inner",validate="one_to_one")
    linked=linked.dropna(subset=["continent","koppen_broad"])
    linked=linked.loc[(linked.continent.astype(str)!="Unknown")&
                      (linked.koppen_broad.astype(str)!="Unknown")]
    if linked.empty:raise ValueError("No valid official UCDB + climate GF10 overlaps")
    valid=[];skipped=[]
    for row in linked.itertuples(index=False):
        try:wgs84_ring(row.grid_x,row.grid_y)
        except ValueError:
            skipped.append(row.grid_id)
            continue
        valid.append(row.grid_id)
    linked=linked.loc[linked.grid_id.isin(valid)].copy()
    eligible=linked[["city_id","continent","koppen_broad"]].drop_duplicates()
    eligible["stratum"]=eligible.continent.astype(str)+"|"+eligible.koppen_broad.astype(str)
    eligible["order"]=eligible.city_id.map(lambda s:rank(s,seed))
    if frozen_v3:
        v3=pd.read_csv(frozen_v3)
        required={"city_id","fig1_v3_status","eligible_using_only_development_years"}
        if required-set(v3):
            raise ValueError("Figure1 v3 must contain development-only split and eligibility")
        v3["city_id"]=v3.city_id.astype(str)
        if v3.city_id.duplicated().any():raise ValueError("Duplicate v3 official UCDB city")
        eligible=eligible.merge(v3[list(required)],on="city_id",how="inner",
                                validate="one_to_one")
        iseligible=eligible.eligible_using_only_development_years.astype(str).str.lower().isin(
            ["true","1"])
        eligible=eligible.loc[iseligible & eligible.fig1_v3_status.isin(
            ["TRAIN_CANDIDATE","HELDOUT_CITY_CANDIDATE"])].copy()
    def round_robin(frame,limit):
        by_stratum={}
        for stratum,part in frame.groupby("stratum"):
            by_stratum[stratum]=part.sort_values("order").city_id.tolist()
        chosen=[]
        while len(chosen)<limit and any(by_stratum.values()):
            for name in sorted(by_stratum):
                if by_stratum[name]:
                    chosen.append(by_stratum[name].pop(0))
                    if len(chosen)>=limit:break
        return chosen
    if frozen_v3:
        n_held=max(2,round(.2*max_cities))
        held=round_robin(eligible[eligible.fig1_v3_status.eq(
            "HELDOUT_CITY_CANDIDATE")],n_held)
        train=round_robin(eligible[eligible.fig1_v3_status.eq(
            "TRAIN_CANDIDATE")],max_cities-n_held)
        if len(held)<2 or len(train)<3:
            raise ValueError("Too few frozen v3 train and heldout city candidates")
        chosen=train+held
    else:
        train=held=[]
        chosen=round_robin(eligible,max_cities)
    if len(chosen)<5:
        raise ValueError("Too few cities under observed climate/continent strata")
    rows=[]
    for city in chosen:
        local=linked.loc[linked.city_id==city].copy()
        local["order"]=local.grid_id.map(lambda s:rank(s,seed))
        rows.extend(local.sort_values("order").head(cells_per_city).grid_id.tolist())
    result=grid.loc[grid.grid_id.isin(rows)].copy().sort_values("grid_id")
    if result.grid_id.duplicated().any() or len(result)!=len(set(rows)):
        raise ValueError("GF10 sample selection integrity failure")
    summary={"status":"STRATIFIED_GEOGRAPHIC_DESIGN_NOT_MODEL_EVIDENCE",
             "cities":len(chosen),"grid_cells":len(result),"seed":seed,
             "max_cities":max_cities,"cells_per_city":cells_per_city,
             "independent_of_news_labels":frozen_v3 is None,
             "independent_of_2024_2025_news":True,
             "used_2021_2023_reporting_eligibility":bool(frozen_v3),
             "frozen_train_cities":len(train),
             "frozen_heldout_cities":len(held),
             "frozen_v3_file":str(frozen_v3) if frozen_v3 else None,
             "source_grid_crs":"EPSG:6933","cell_size_m":10000,
             "antimeridian_excluded_grid_ids":skipped[:200],
             "antimeridian_excluded_count":len(skipped),
             "warning":"Representative pilot geography, not probability sample of global flood incidence"}
    return result,summary


def build(root,grid,crosswalk,cities,tag="fig2_subset_v2",
          max_cities=40,cells_per_city=12,seed=42,frozen_v3=None):
    if not tag.startswith("fig2_") or "/" in tag or "\\" in tag:
        raise ValueError("Invalid version tag")
    out=safe_output(root,"data/reference/"+tag)
    if out.exists():raise FileExistsError("Sample already exists: "+str(out))
    frame,qc=sample(grid,crosswalk,cities,max_cities,cells_per_city,seed,frozen_v3)
    out.mkdir(parents=True,exist_ok=False)
    frame.to_parquet(out/"fig2_GF10_selected_grid.parquet",index=False)
    atomic_json(out/"fig2_GF10_sample_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--crosswalk",type=Path,required=True)
    p.add_argument("--cities",type=Path,required=True)
    p.add_argument("--max-cities",type=int,default=40)
    p.add_argument("--cells-per-city",type=int,default=12)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--city-audit-v3",type=Path,
                   help="Frozen 2021-23 Figure1 v3 city assignment; sample BOTH train/heldout strata")
    p.add_argument("--tag",default="fig2_subset_v2")
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,a.grid,a.crosswalk,a.cities,
                           a.tag,a.max_cities,a.cells_per_city,a.seed,a.city_audit_v3),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":main()
