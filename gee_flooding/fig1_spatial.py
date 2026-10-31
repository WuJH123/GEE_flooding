"""Frozen GF10 core plus audited 1-cell (10 km) surrounding lattice.

Read existing 2020 EPSG:6933 SMOD stripes, never download or change inputs.
Only valid adjacent raster cells can be classified as PERIPHERAL. An urban
study core is the pre-existing 166k approved frame, never recomputed.
"""
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
import rasterio
from .paths import safe_output,atomic_json

def freeze_periphery(root,core,west,east,tag="fig1_publication_v1",min_valid=.95):
    core=pd.read_parquet(core)
    cols={"grid_id","grid_x","grid_y"}
    if cols-set(core):raise ValueError("Missing frozen core grid identifiers")
    if core.grid_id.duplicated().any():raise ValueError("Duplicate urban grid identifiers")
    if not 0<min_valid<=1:raise ValueError("Invalid raster validity minimum")
    out=safe_output(root,f"outputs/{tag}/grid")
    if out.exists():raise FileExistsError(out)
    known=set(zip(core.grid_x.astype(int),core.grid_y.astype(int)))
    adjacent=set()
    for x,y in known:
        for i in (-1,0,1):
            for j in (-1,0,1):
                if i or j:
                    p=(x+i,y+j)
                    if p not in known:adjacent.add(p)
    result=[];reject=Counter()
    # Filename-independent stripe selection via actual affine transform.
    for p in [west,east]:
        with rasterio.open(p) as ds:
            if ds.crs is None or ds.crs.to_epsg()!=6933 or ds.count!=2:
                raise ValueError(f"Expected two-band EPSG6933 SMOD stripe: {p}")
            tr=ds.transform
            if abs(tr.a-10000)>1e-4 or abs(tr.e+10000)>1e-4 or abs(tr.b)>1e-4 or abs(tr.d)>1e-4:
                raise ValueError("GF10 raster affine must be exact 10 km projected lattice")
            if abs(tr.c/10000-round(tr.c/10000))>1e-6 or abs(tr.f/10000-round(tr.f/10000))>1e-6:
                raise ValueError("GF10 stripe origin not aligned to 10km grid")
            minx=int(round(tr.c/10000))
            maxy=int(round(tr.f/10000))
            # choose only adjacent cells within this stripe; no pre-emptive
            # reads of full global 100m source imagery.
            pairs=[(x,y) for x,y in adjacent if minx<=x<minx+ds.width
                   and maxy-ds.height<=y<maxy]
            if not pairs:continue
            x=np.asarray([t[0] for t in pairs]);y=np.asarray([t[1] for t in pairs])
            columns=x-minx;rows=maxy-y-1
            urb=ds.read(1,masked=True)
            valid=ds.read(2,masked=True)
            u=np.asarray(urb[rows,columns].filled(np.nan) if np.ma.isMaskedArray(urb[rows,columns])
                         else urb[rows,columns],dtype=float)
            v=np.asarray(valid[rows,columns].filled(np.nan) if np.ma.isMaskedArray(valid[rows,columns])
                         else valid[rows,columns],dtype=float)
            good=np.isfinite(v)&(v>=min_valid)&np.isfinite(u)&(u>=0)&(u<=v+1e-5)
            for k,(xx,yy) in enumerate(pairs):
                if not good[k]:
                    reject["FAILED_RASTER_VALIDITY"]+=1
                    continue
                result.append((xx,yy,float(u[k]),float(v[k])))
    if not result:raise ValueError("No valid periphery cells; check the two source stripes")
    g=pd.DataFrame(result,columns=["grid_x","grid_y","urban_fraction_2020","source_valid_fraction"])
    g["grid_id"]=[f"{x}_{y}" for x,y in zip(g.grid_x,g.grid_y)]
    if g.grid_id.duplicated().any():raise ValueError("Overlapping SMOD stripes or repeated grid ID")
    g["domain"]="PERIPHERY_10KM_RING"
    g["longitude"]=np.nan;g["latitude"]=np.nan
    # Centroids transformed from exact equal-area raster lattice, not flood locations.
    from pyproj import Transformer
    lng,lat=Transformer.from_crs(6933,4326,always_xy=True).transform(
        (g.grid_x.to_numpy()+.5)*10000,(g.grid_y.to_numpy()+.5)*10000)
    g["longitude"]=lng;g["latitude"]=lat
    c=core[["grid_id","grid_x","grid_y","longitude","latitude"]].copy()
    c["domain"]="GF10_2020_URBAN_CORE"
    frame=pd.concat([c,g[["grid_id","grid_x","grid_y","longitude","latitude","domain"]]],
                    ignore_index=True)
    if frame.grid_id.duplicated().any():raise ValueError("Core/periphery overlap")
    out.mkdir(parents=True,exist_ok=False)
    frame.to_parquet(out/"gf10_core_periphery_2020.parquet",index=False)
    g.to_parquet(out/"gf10_periphery_2020.parquet",index=False)
    qc={"status":"PASS_FROZEN_SPATIAL_LATTICE","urban_core_cells":len(c),
        "valid_one_cell_periphery":len(g),"total_frame":len(frame),
        "unresolved_adjacent_cells":len(adjacent)-len(g),
        "source_rejects":dict(reject),
        "crs":"EPSG:6933","cell_size_m":10000,
        "policy":"2020 static frame for all news dates; periphery is exposure geography, not observed flood/nonflood"}
    atomic_json(out/"spatial_frame_qc.json",qc)
    return qc
