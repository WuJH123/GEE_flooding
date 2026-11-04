"""Exact EPSG6933 frozen 10km indices and independent-outcome study scopes."""
from __future__ import annotations
from pathlib import Path
import hashlib
from .contract import GRID_N, GRID_LAND_KM2, CELL_METERS

def read_grid(path, strict=True):
    import pandas as pd
    cols=['grid_id','grid_x','grid_y','land_area_km2']
    frame=pd.read_parquet(path,columns=cols)
    if frame.grid_id.isna().any() or frame.grid_id.duplicated().any():raise ValueError('Duplicate / null grid_id')
    expected=frame.grid_x.astype(str)+'_'+frame.grid_y.astype(str)
    if not (expected==frame.grid_id.astype(str)).all():raise ValueError('GF10 ID is not x_y frozen key')
    if not frame.land_area_km2.between(0,100.00001,inclusive='right').all():raise ValueError('Invalid land area')
    if strict and (len(frame)!=GRID_N or abs(frame.land_area_km2.sum()-GRID_LAND_KM2)>0.02):
        raise ValueError('Frozen GF10 global registry checksum mismatch')
    return frame

def block_id(x,y,dimension):
    if dimension<=0:raise ValueError('Invalid tile dimension')
    return (int(x)//dimension*dimension,int(y)//dimension*dimension)

def make_plan(grid, family, selected_ids=None):
    """Plan one bounded 10x10 MERIT or 5x5 WorldCover task per nonempty block."""
    import pandas as pd
    dim=10 if family=='merit' else 5
    if selected_ids is not None:
        ids=set(str(x) for x in selected_ids)
        if not ids:raise ValueError('Empty/unspecified pre-frozen study cohort')
        if not ids.issubset(set(grid.grid_id.astype(str))):raise ValueError('Unknown GF10 study IDs')
        grid=grid[grid.grid_id.astype(str).isin(ids)]
    tx=(grid.grid_x//dim)*dim
    ty=(grid.grid_y//dim)*dim
    p=pd.DataFrame({'tile_x0':tx,'tile_y0':ty,'grid_id':grid.grid_id}).groupby(
        ['tile_x0','tile_y0'],sort=True).agg(n_land_cells=('grid_id','count')).reset_index()
    p['family']=family
    p['tile_size']=dim
    p['tile_key']=[f'{family}_{x}_{y}_{dim}' for x,y in zip(p.tile_x0,p.tile_y0)]
    p['n_work_pixels']=dim*dim
    return p[['family','tile_key','tile_x0','tile_y0','tile_size','n_land_cells','n_work_pixels']]

def tile_bounds(x,y,n):
    return [int(x)*CELL_METERS,int(y)*CELL_METERS,(int(x)+int(n))*CELL_METERS,(int(y)+int(n))*CELL_METERS]

def frozen_sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def event_plan_from_records(events,grid,years=(2021,2022,2023,2024,2025)):
    """Reject any 20km/old IDs; never infer no-report as a negative flood."""
    import pandas as pd
    if not {'grid_id','date_utc'}.issubset(events.columns):
        raise ValueError('Event cohort requires frozen GF10 grid_id and date_utc')
    values=events[['grid_id','date_utc']].copy()
    values['grid_id']=values.grid_id.astype(str)
    if not set(values.grid_id).issubset(set(grid.grid_id.astype(str))):
        raise ValueError('Event grid_id absent from GF10; upstream 20km event data must be remapped, not guessed')
    parsed=pd.to_datetime(values.date_utc,utc=True,errors='raise')
    if not parsed.dt.hour.eq(0).all() or not parsed.dt.minute.eq(0).all():
        raise ValueError('date_utc must be UTC midnight, not event timestamps or local dates')
    values['date_utc']=parsed.dt.strftime('%Y-%m-%d')
    if not set(parsed.dt.year.unique()).issubset(set(years)):
        raise ValueError('Study years outside prospectively defined 2021–2025 interval')
    values=values.drop_duplicates(['grid_id','date_utc'])
    joined=values.merge(grid[['grid_id','grid_x','grid_y']],on='grid_id',validate='many_to_one')
    joined['tile_x0']=joined.grid_x//10*10
    joined['tile_y0']=joined.grid_y//10*10
    plan=(joined.groupby(['date_utc','tile_x0','tile_y0'])
          .agg(n_unique_grid_days=('grid_id','count')).reset_index().sort_values(['date_utc','tile_x0','tile_y0']))
    plan['tile_key']=[f'event_{date}_{x}_{y}' for date,x,y in zip(plan.date_utc,plan.tile_x0,plan.tile_y0)]
    return joined,plan
