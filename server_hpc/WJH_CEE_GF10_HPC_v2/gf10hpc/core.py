from __future__ import annotations
import hashlib,json,os,re,tempfile,time
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_N=1_395_471
EXPECTED_AREA_KM2=133_095_959.350
GF_CELL_M=10_000
REQUIRED={'grid_id','land_area_km2'}

def digest(path: Path, chunk=8<<20):
    d=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(chunk), b''): d.update(b)
    return d.hexdigest()

def json_write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.writing')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    os.replace(tmp,path)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def file_identity(path):
    p=Path(path);s=p.stat()
    return {'path':str(p.resolve()),'size':s.st_size,'mtime_ns':s.st_mtime_ns}

def require_nonexistent(path):
    if Path(path).exists(): raise FileExistsError(f'New versioned output required: {path}')

def safe_hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def grid_indices(df):
    df=df.copy()
    if not REQUIRED.issubset(df.columns):raise ValueError('Frozen GF10 missing '+str(REQUIRED-set(df.columns)))
    df['grid_id']=df['grid_id'].astype(str)
    if {'grid_x','grid_y'}<=set(df.columns):
        x=pd.to_numeric(df['grid_x'],errors='raise').to_numpy(dtype='int64')
        y=pd.to_numeric(df['grid_y'],errors='raise').to_numpy(dtype='int64')
    else:
        parsed=df.grid_id.str.extract(r'^(-?\d+)_(-?\d+)$')
        if parsed.isna().any().any():raise ValueError('Expected original GF10 grid_id=x_y')
        x=parsed[0].to_numpy(dtype='int64');y=parsed[1].to_numpy(dtype='int64')
        df['grid_x']=x;df['grid_y']=y
    got=np.char.add(np.char.add(x.astype(str),'_'),y.astype(str))
    if not np.array_equal(got,df.grid_id.to_numpy()):raise ValueError('Frozen grid_id mismatch')
    return df

def audit_grid(path, full=True):
    p=Path(path); df=grid_indices(pd.read_parquet(p))
    if df.grid_id.duplicated().any():raise ValueError('GF10 has duplicate IDs')
    if 'grid_crs' in df and not df.grid_crs.astype(str).isin(('EPSG:6933','6933')).all():
        raise ValueError('Only frozen nonantarctic EPSG:6933 is accepted')
    a=pd.to_numeric(df.land_area_km2, errors='coerce')
    if not np.isfinite(a).all() or not a.gt(0).all() or not a.le(100.00001).all():
        raise ValueError('GF10 nonpositive/invalid land area')
    if 'land_fraction' in df and not np.allclose(df.land_fraction,a/100,atol=1e-5,rtol=0):
        raise ValueError('land_fraction inconsistent with km2')
    if full and (len(df)!=EXPECTED_N or abs(a.sum()-EXPECTED_AREA_KM2)>100):
        raise ValueError('GF10 does not match frozen nonantarctic reference')
    return {'status':'GRID_SCHEMA_PASS_NOT_INDEPENDENT_GSHHG_AUDIT',
            'n_grid':len(df),'land_area_km2':float(a.sum()),
            'partial_land_cells':int(a.lt(99.9999).sum()),
            'tiny_land_cells_under_1km2':int(a.lt(1).sum()),
            'grid_sha256':digest(p),'grid_crs':'EPSG:6933'}

def tile_index(grid, out, side=64, full=True):
    g=grid_indices(pd.read_parquet(grid)); audit=audit_grid(grid,full)
    if not 16<=side<=128: raise ValueError('tile cells must be 16..128')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    done=out/'tile_index_qc.json'
    fingerprint={'grid_sha256':audit['grid_sha256'],'side':side,'schema':'tile_v2'}
    if done.exists():
        existing=read_json(done)
        if existing.get('job_id')!=safe_hash(fingerprint):raise ValueError('Tile directory belongs to different grid or side')
        files=list((out/'tiles').glob('*.parquet'))
        if len(files)!=existing['n_tiles']:raise ValueError('Existing tile collection incomplete')
        return existing
    if (out/'tiles').exists() and any((out/'tiles').iterdir()):
        raise FileExistsError('Unverified previous tile files; use new tile version')
    g['tile_x']=np.floor_divide(g.grid_x.to_numpy(dtype='int64'),side)
    g['tile_y']=np.floor_divide(g.grid_y.to_numpy(dtype='int64'),side)
    (out/'tiles').mkdir(exist_ok=True)
    items=[]
    # tile must have only one GF10 per coordinate and be independent of original row order
    keep=['grid_id','grid_x','grid_y','land_area_km2','tile_x','tile_y']
    if 'land_fraction' in g.columns: keep.append('land_fraction')
    for (tx,ty),sub in g.groupby(['tile_x','tile_y'],sort=True):
        name=f'tile_{tx:+05d}_{ty:+05d}.parquet'
        sub[keep].sort_values(['grid_x','grid_y']).to_parquet(out/'tiles'/name,index=False,compression='zstd')
        items.append({'tile_x':int(tx),'tile_y':int(ty),'tile_file':name,'n_grid':len(sub),'land_km2':float(sub.land_area_km2.sum())})
    pd.DataFrame(items).to_parquet(out/'index.parquet',index=False)
    res={'job_id':safe_hash(fingerprint),**audit,'tile_size':side,'n_tiles':len(items),'n_grid':len(g),'status':'TILES_COMPLETE'}
    json_write(done,res)
    return res
