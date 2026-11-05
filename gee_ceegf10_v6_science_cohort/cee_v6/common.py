"""Immutable provenance and strict user-supplied file compatibility."""
from __future__ import annotations
import hashlib,json,os,pathlib,datetime as dt
P=pathlib.Path
ROOT=P(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def save(path,data,overwrite=False):
    path=P(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not overwrite:raise FileExistsError(f'Immutable output exists: {path}')
    t=path.with_name(path.name+'.writing')
    with open(t,'w',encoding='utf8') as f:json.dump(data,f,indent=2,ensure_ascii=False,default=str)
    os.replace(t,path)

def load(path):return json.loads(P(path).read_text('utf8'))

def now():return dt.datetime.now(dt.timezone.utc).isoformat()

def readtab(path,columns=None):
    import pandas as pd
    p=P(path)
    if not p.is_file():raise FileNotFoundError(p)
    if p.suffix.lower() in ('.parquet','.pq'):
        return pd.read_parquet(p,columns=columns)
    if p.suffix.lower()=='.csv':return pd.read_csv(p,usecols=columns,dtype={'grid_id':'string'})
    raise ValueError('Only parquet or CSV accepted: '+str(p))

def writetab(frame,path):
    p=P(path);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError('Immutable table exists: '+str(p))
    frame.to_parquet(p,index=False)

def source_columns(path):
    p=P(path)
    if p.suffix.lower()=='.parquet':
        import pyarrow.parquet as pq
        return pq.read_schema(p).names
    import pandas as pd
    return list(pd.read_csv(p,nrows=0).columns)

GF10_SHA='4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d'
GF10_COUNT=1395471
GF10_LAND_KM2=133095959.350
PROJECT='future-shuttle-513705-g9'
FINAL_V07_END='2025-09-30'

def check_grid(path,strict=True):
    import pandas as pd
    if strict and sha(path)!=GF10_SHA:raise ValueError('GF10 SHA differs from v5 authoritative result')
    g=readtab(path,['grid_id','grid_x','grid_y','land_area_km2'])
    if g.grid_id.isna().any() or g.grid_id.duplicated().any():raise ValueError('GF10 null or duplicate ID')
    if not (g.grid_x.astype(str)+'_'+g.grid_y.astype(str)==g.grid_id.astype(str)).all():raise ValueError('GF10 coordinate and ID mismatch')
    if strict and (len(g)!=GF10_COUNT or abs(g.land_area_km2.sum()-GF10_LAND_KM2)>.05):
        raise ValueError('GF10 count/land area mismatch')
    return g
