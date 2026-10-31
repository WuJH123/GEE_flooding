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


def sample(grid,crosswalk,city_meta,max_cities=40,cells_per_city=12,seed=42):
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
    by_stratum={}
    for stratum,part in eligible.groupby("stratum"):
        by_stratum[stratum]=part.sort_values("order").city_id.tolist()
    chosen=[]
    # Round-robin climate/continent groups: no dependence on news outcomes.
    while len(chosen)<max_cities and any(by_stratum.values()):
        for name in sorted(by_stratum):
            if by_stratum[name]:
                chosen.append(by_stratum[name].pop(0))
                if len(chosen)>=max_cities:break
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
             "independent_of_news_labels":True,
             "source_grid_crs":"EPSG:6933","cell_size_m":10000,
             "antimeridian_excluded_grid_ids":skipped[:200],
             "antimeridian_excluded_count":len(skipped),
             "warning":"Representative pilot geography, not probability sample of global flood incidence"}
    return result,summary


def build(root,grid,crosswalk,cities,tag="fig2_subset_v2",
          max_cities=40,cells_per_city=12,seed=42):
    if not tag.startswith("fig2_") or "/" in tag or "\\" in tag:
        raise ValueError("Invalid version tag")
    out=safe_output(root,"data/reference/"+tag)
    if out.exists():raise FileExistsError("Sample already exists: "+str(out))
    frame,qc=sample(grid,crosswalk,cities,max_cities,cells_per_city,seed)
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
    p.add_argument("--tag",default="fig2_subset_v2")
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,a.grid,a.crosswalk,a.cities,
                           a.tag,a.max_cities,a.cells_per_city,a.seed),
                     ensure_ascii=False,indent=2))


if __name__=="__main__":main()
