"""Atomic outputs, provenance and frozen-grid protection."""
from __future__ import annotations
from pathlib import Path
import json, os, hashlib, time, math

def atomic_json(path, data):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.writing')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    os.replace(tmp,p)

def atomic_parquet(df,path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.writing')
    df.to_parquet(tmp,index=False)
    os.replace(tmp,p)

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def fidentity(path):
    p=Path(path);s=p.stat()
    return {'path':str(p.resolve()),'length':s.st_size,'mtime_ns':s.st_mtime_ns}

def job_id(spec):return hashlib.sha256(json.dumps(spec,sort_keys=True,default=str).encode('utf8')).hexdigest()

def ensure_job(out,spec):
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    j=job_id(spec);manifest=p/'job.json'
    if manifest.exists():
        prev=read_json(manifest)
        if prev.get('job_id')!=j:raise ValueError('Different source/config in existing output; choose a new version directory: '+str(p))
    else:
        if any(p.iterdir()):raise FileExistsError('Untracked files in output directory '+str(p))
        atomic_json(manifest,{'job_id':j,'spec':spec,'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    return j

def verify_frozen_grid(grid,strict=True):
    import pandas as pd
    g=pd.read_parquet(grid)
    required={'grid_id','grid_x','grid_y','land_area_km2'}
    missing=required-set(g.columns)
    if missing:raise ValueError('GF10 missing required columns: '+str(sorted(missing)))
    if g.grid_id.isna().any() or g.grid_id.duplicated().any():raise ValueError('GF10 grid_id missing or duplicated')
    if (g.land_area_km2<=0).any() or (g.land_area_km2>100.0001).any():raise ValueError('GF10 nonpositive or >100km2 land area')
    if not (pd.api.types.is_integer_dtype(g.grid_x) and pd.api.types.is_integer_dtype(g.grid_y)):
        raise ValueError('GF10 grid_x/grid_y must be integer indices')
    n=len(g); total=float(g.land_area_km2.sum())
    if strict and (n!=1395471 or abs(total-133095959.350)>2):
        raise ValueError('GF10 does not match frozen nonantarctic v1: '+str((n,total)))
    return g,{'n_cells':n,'unique_grid_ids':n,'total_land_area_km2':total,
              'partial_land_cells':int((g.land_area_km2<99.999).sum()),
              'tiny_land_cells_under_1km2':int((g.land_area_km2<1).sum()),
              'grid_crs':'EPSG:6933','source':fidentity(grid),'strict':strict}

def gf10_bounds(x,y):
    """Frozen grid indexing: 10km cells with origin at EPSG:6933 (0,0)."""
    x=int(x);y=int(y)
    return (x*10000,y*10000,(x+1)*10000,(y+1)*10000)
