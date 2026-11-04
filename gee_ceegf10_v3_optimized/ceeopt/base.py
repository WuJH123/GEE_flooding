"""Immutable GF10 reference, source identity and crash-safe checkpoint utilities."""
from __future__ import annotations
import hashlib,json,os,datetime as dt
from pathlib import Path

GRID_N=1_395_471
GRID_LAND_KM2=133_095_959.350
WC_CLASSES=(10,20,30,40,50,60,70,80,90,95,100)
M1_FIELDS=(
 'merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2',
 'merit_permanent_water_fraction','merit_valid_fraction',
 'merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
 'merit_hand_le10_fraction_valid','merit_slope_mean_deg',
 'merit_slope_le2_fraction_valid','merit_upa_max_km2',
 'merit_upa_max_log1p','merit_hand_p10_m','merit_hand_p50_m',
 'merit_hand_p90_m','merit_upa_p90_km2')
WC_FIELDS=(tuple(f'wc_{c}_fraction_fullcell' for c in WC_CLASSES)
         +('wc_valid_fraction_fullcell',)
         +tuple(f'wc_{c}_fraction_land' for c in WC_CLASSES)
         +('wc_valid_fraction_land','wc_gshhg_land_fraction_raster'))

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def atomic_json(path,obj):
    p=Path(path);p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_name(p.name+'.tmp')
    with tmp.open('w',encoding='utf8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,sort_keys=True,default=str)
    os.replace(tmp,p)

def load_json(path,default=None):
    p=Path(path)
    return json.loads(p.read_text(encoding='utf8')) if p.is_file() else default

def load_gf10(path,strict=True):
    import pandas as pd
    p=Path(path)
    if not p.exists():raise FileNotFoundError(p)
    g=pd.read_parquet(p,columns=['grid_id','grid_x','grid_y','land_area_km2'])
    if g.grid_id.isna().any() or g.grid_id.duplicated().any():raise ValueError('Frozen grid_id invalid')
    if not (g.grid_id.astype(str)==g.grid_x.astype(str)+'_'+g.grid_y.astype(str)).all():
        raise ValueError('GF10 IDs differ from frozen lattice x_y')
    if not ((g.land_area_km2>0)&(g.land_area_km2<=100.00001)).all():
        raise ValueError('GF10 land area not positive and <=100 km2')
    if strict and (len(g)!=GRID_N or abs(float(g.land_area_km2.sum())-GRID_LAND_KM2)>0.04):
        raise ValueError('Frozen non-Antarctic GF10 row count or land area mismatch')
    return g

def frozen_grid(root):
    root=Path(root)
    options=[root/'gf10_global_nonantarctic_land.parquet',
             root/'gee_ceegf10_v1'/'config'/'local_run.json']
    if options[0].is_file():return options[0]
    if options[1].is_file():
        c=load_json(options[1]);p=Path(c['grid'])
        if p.is_file():return p
    for p in [root/'data'/'reference'/'gf10_global_nonantarctic_land.parquet']:
        if p.is_file():return p
    raise FileNotFoundError('Copy frozen GF10 to E:\\WJH_CEE\\gf10_global_nonantarctic_land.parquet or configure existing CEE GEE v1')

def utc_now():return dt.datetime.now(dt.timezone.utc).isoformat()

def check_output_identity(directory,source):
    """Do not mix two independent source sets or workflows in one output dir."""
    d=Path(directory); d.mkdir(parents=True,exist_ok=True)
    config=d/'product_identity.json'
    current=load_json(config)
    if current is None:
        if any(d.iterdir()):raise FileExistsError('Output dir not empty but no provenance manifest: '+str(d))
        atomic_json(config,source)
    elif current!=source:
        raise ValueError('Existing output identity differs; use a NEW product version: '+str(d))
    return d
