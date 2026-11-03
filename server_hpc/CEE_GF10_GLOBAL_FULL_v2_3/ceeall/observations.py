"""Flood events are catalogues/positive reports, not true pluvial flooded masks."""
from pathlib import Path
from .common import atomic_json,atomic_parquet

def read_flood_catalogue(root,source=None):
    import pandas as pd
    root=Path(root)
    source=Path(source) if source else root/'CEE数据/Global_Flood_Records.csv'
    if not source.is_file():raise FileNotFoundError(source)
    x=pd.read_csv(source,encoding='utf-8-sig')
    required=['Start Date','End Date','Country','Main Cause']
    missing=set(required)-set(x.columns)
    if missing:raise ValueError('Flood catalogue schema mismatch '+str(missing))
    x['start_date_utc']=pd.to_datetime(x['Start Date'],errors='coerce',utc=True)
    x['end_date_utc']=pd.to_datetime(x['End Date'],errors='coerce',utc=True)
    if x.start_date_utc.isna().mean()>.05:raise ValueError('Many unparsed start dates')
    x['not_city_pluvial_ground_truth']=True
    out=root/'data/derived/cee_all_v11/flood_catalogue'
    if out.exists():raise FileExistsError('Versioned flood catalogue output exists; do not overwrite')
    out.mkdir(parents=True)
    atomic_parquet(x,out/'events.parquet')
    atomic_json(out/'qc.json',{'status':'EVENT_CONTEXT_NOT_PHYSICAL_FLOOD_VALIDATION',
       'n_rows':len(x),'unparseable_start':int(x.start_date_utc.isna().sum()),
       'not_negative_samples':True,'source':str(source)})
    return {'n_rows':len(x),'out':str(out)}
