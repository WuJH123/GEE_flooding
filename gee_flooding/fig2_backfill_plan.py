"""Create *no-submit* bounded Earth Engine backfill tasks from real GF10 NaNs.

Rows/indicators are computed from a previously audited merged wide table,
not an assumed 40-city output or a whole-world re-extraction. Similar missing
band signatures are grouped by physical source family, then capped into
<=20-cell table tasks. No data is downloaded and no job is submitted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import pandas as pd
from .fig2_gee import GEE_STATIC,EXPOSURE
from .fig2_indicators import CORE
from .paths import safe_output,atomic_json

FAMILIES={
    "merit":("static",["hand_m","elevation_m","slope_deg",
                       "upstream_area_km2","river_water_fraction"]),
    "landcover":("static",["vegetation_fraction","tree_fraction",
                           "grass_fraction","cropland_fraction","wetland_fraction",
                           "water_fraction","bare_fraction"]),
    "builtform":("static",["built_fraction_2020","built_fraction_2000","built_nres_fraction_2020",
                          "built_neighbor_density","built_fragmentation",
                          "built_growth_2000_2020"]),
    "population":("exposure",list(EXPOSURE)),
}
assert set().union(*(set(v[1]) for v in FAMILIES.values()))==set(GEE_STATIC)|set(EXPOSURE)


def plan(root,grid,integrated,tag="fig2_backfill_pilot_v1",
         max_cells=20,scope="core",max_tasks=1000):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use a new fig2_* versioned task plan tag")
    if not 1<=max_cells<=30 or not 1<=max_tasks<=10000:
        raise ValueError("Bound each static backfill task to <=30 GF10, at most 10000 planned tasks")
    if scope not in ("core","extended"):
        raise ValueError("scope must be core or extended")
    frozen=pd.read_parquet(grid).copy()
    current=pd.read_parquet(integrated).copy()
    required={"grid_id","grid_x","grid_y","urban_fraction_2020"}
    if required-set(frozen) or "grid_id" not in current:
        raise ValueError("Frozen GF10/index mismatch")
    for x in (frozen,current):
        x["grid_id"]=x.grid_id.astype(str)
        if x.grid_id.duplicated().any():raise ValueError("Duplicate GF10 grid_id")
    if not set(current.grid_id).issubset(set(frozen.grid_id)):
        raise ValueError("Existing indicator table includes other non-frozen grids")
    current=current.set_index("grid_id")
    jobs=[]
    sections=[]
    for family,(mode,bands) in FAMILIES.items():
        active=[b for b in bands if scope=="extended" or b in CORE or b in EXPOSURE]
        if not active:continue
        pattern={}
        for row in frozen.itertuples(index=False):
            k=str(row.grid_id)
            needed=tuple(b for b in active if
                         (b not in current or k not in current.index
                          or pd.isna(current.loc[k,b])))
            if needed:pattern.setdefault(needed,[]).append(k)
        for group_index,(signature,ids) in enumerate(sorted(pattern.items(),key=lambda z:z[0])):
            for st in range(0,len(ids),max_cells):
                batch=ids[st:st+max_cells]
                sub=frozen.loc[frozen.grid_id.isin(batch)].copy()
                sub=sub.sort_values("grid_id")
                if len(sub)!=len(batch):raise ValueError("Missing/duplicate frozen grid batch")
                digest=hashlib.sha256((family+"|"+",".join(signature)+"|"+",".join(sub.grid_id)).encode()).hexdigest()[:12]
                job_id=f"{family}_{digest}"
                jobs.append(dict(job_id=job_id,source_family=family,mode=mode,
                                 bands=",".join(signature),n_grid=len(sub),
                                 min_grid_id=min(batch),max_grid_id=max(batch),
                                 grid_file="grids/"+job_id+".parquet",
                                 state="PLANNED_NOT_SUBMITTED"))
                sections.append((job_id,sub))
    if not jobs:raise ValueError("No missing GEE static/exposure indicators in this scope")
    if len(jobs)>max_tasks:
        raise ValueError("Too many pending jobs: "+str(len(jobs))+
                         ". Scope/regions must be narrowed before task export")
    output=safe_output(root,"data/reference/"+tag)
    if output.exists():raise FileExistsError("Immutable version exists: "+str(output))
    (output/"grids").mkdir(parents=True,exist_ok=False)
    for k,df in sections:
        df.to_parquet(output/"grids"/(k+".parquet"),index=False)
    task=pd.DataFrame(jobs)
    task.to_csv(output/"fig2_gee_backfill_tasks.csv",index=False)
    # Generated commands do not submit GEE work or download anything.
    commands=['# Plan only: inspect each dry run; add --project PROJECT --submit manually.',
              '$ROOT="E:\\GEE_flooding"',
              '$PY="$ROOT\\.venv\\Scripts\\python.exe"']
    for row in jobs:
        grid_file=str(output/row["grid_file"])
        commands.append(f'& $PY -m gee_flooding.fig2_gee --grid "{grid_file}" '
                        f'--mode {row["mode"]} --bands {row["bands"]} '
                        f'--start-row 0 --count {row["n_grid"]}')
    (output/"fig2_gee_backfill_dry_runs.ps1").write_text(
        "\n".join(commands)+"\n",encoding="utf-8-sig")
    qc=dict(status="GEE_STATIC_GAP_PLAN_NOT_SUBMITTED",scope=scope,
            n_frozen_cells=len(frozen),n_planned_jobs=len(jobs),
            planned_cell_rows=int(task.n_grid.sum()),
            source_families=sorted(set(task.source_family)),
            all_geometries_are_original_GF10=True,
            user_must_review_tasks=True,remote_submissions=0,
            limitations="No GEE values checked until task COMPLETED and downloaded CSV validated")
    atomic_json(output/"fig2_gee_backfill_plan_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--indicators",type=Path,required=True)
    p.add_argument("--tag",default="fig2_backfill_pilot_v1")
    p.add_argument("--scope",choices=["core","extended"],default="core")
    p.add_argument("--max-cells",type=int,default=20)
    a=p.parse_args(argv)
    print(json.dumps(plan(a.root,a.grid,a.indicators,a.tag,a.max_cells,a.scope),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
