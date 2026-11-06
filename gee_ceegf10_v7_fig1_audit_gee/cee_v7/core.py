"""Immutable provenance, GF10 identity and strict publication rules."""
from __future__ import annotations
import csv,datetime as dt,hashlib,json,os,pathlib,tempfile
from typing import Any

NAME='CEE_GF10_FIG1_AUDIT_GEE_V7_20261106'
PROJECT='future-shuttle-513705-g9'
GF10_HASH='4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d'
GF10_ROWS=1395471
PRODUCT='Groundsource v1 2026; https://doi.org/10.5281/zenodo.18647054'
PERMANENT_END='2025-09-30'
EPS=1e-10


def digest(path,buf=4*1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(buf),b''):h.update(b)
    return h.hexdigest()

def read_json(path,default=None):
    p=pathlib.Path(path)
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default

def write_json(path,data,replace=False):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and not replace:
        raise FileExistsError('Immutable output already exists: '+str(p))
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.tmp-',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True,default=str);f.write('\n')
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.remove(tmp)
    return str(p)

def stable_id(*parts,n=24):
    return hashlib.sha256('|'.join(str(s) for s in parts).encode('utf8')).hexdigest()[:n]

def day_str(s):
    """ISO calendar date without timezone/time invented; reject datetime timestamps."""
    import pandas as pd
    if s is None or pd.isna(s):return None
    if isinstance(s,(pd.Timestamp,dt.datetime)):
        if any((s.hour,s.minute,s.second,s.microsecond)):return None
        return s.date().isoformat()
    if isinstance(s,dt.date):return s.isoformat()
    s=str(s).strip()
    if len(s)!=10 or s[4]!='-' or s[7]!='-':return None
    try:return dt.date.fromisoformat(s).isoformat()
    except (ValueError,TypeError):return None

def check_grid(path,expected_hash=GF10_HASH,strict=True):
    import pandas as pd
    from pyarrow import parquet as pq
    if strict and digest(path)!=expected_hash:raise ValueError('FROZEN GF10 SHA mismatch')
    fields=set(pq.read_schema(path).names)
    req={'grid_id','grid_x','grid_y','land_area_km2'}
    if not req<=fields:raise ValueError('GF10 missing mandatory columns '+str(req-fields))
    g=pd.read_parquet(path,columns=sorted(req))
    if strict and len(g)!=GF10_ROWS:raise ValueError('Not 1,395,471 frozen GF10 cells')
    if g.grid_id.isna().any() or g.grid_id.duplicated().any():raise ValueError('Duplicate/empty GF10 IDs')
    if g[['grid_x','grid_y']].duplicated().any():raise ValueError('Duplicate GF10 integer cells')
    if not (g.land_area_km2.gt(0)&g.land_area_km2.le(100+1e-4)).all():raise ValueError('Invalid positive land GF10 area')
    if strict and abs(g.land_area_km2.sum()-133095959.3496587)>0.05:raise ValueError('Frozen GF10 area changed')
    g['grid_id']=g.grid_id.astype(str)
    return g

def assert_project(project):
    if project!=PROJECT:raise ValueError('Not the isolated existing CEE Earth Engine project')

def run_conf(out):
    return {'run_id':NAME,'project':PROJECT,'output_root':str(pathlib.Path(out).absolute()),
      'groundsource_origin':PRODUCT,'source_dates_are_utc_inferred':False,
      'physical_flood_truth':False,'output_cells_are_source_geocode_not_inundation':True,
      'snapshot_created_utc':dt.datetime.now(dt.timezone.utc).isoformat()}

def ensure_new(path):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError('Immutable source result exists: '+str(p))
    return p

def as_bool(v):
    if isinstance(v,bool):return v
    if v is None:return False
    if isinstance(v,(int,float)):return v==1
    return str(v).strip().lower() in {'true','1','yes'}
