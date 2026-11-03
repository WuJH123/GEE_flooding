"""Independent C++ native-pixel exactextract audit of fast aligned 1km tiles."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from .core import json_write
from .raster import PROFILES

def compare(src,grid_tile,fast_tile,profile,out,max_cells=500):
    import geopandas as gpd
    import rasterio
    from exactextract import exact_extract
    from shapely.geometry import box
    if profile not in PROFILES:raise KeyError(profile)
    p=PROFILES[profile]
    if p['kind'] not in ('pixel_m2','pixel_count','mean'):
        raise ValueError('exact comparator currently implements only continuous and source-pixel total metrics')
    gf=pd.read_parquet(grid_tile).head(max_cells)
    boxes=[box(x*10000,y*10000,(x+1)*10000,(y+1)*10000)
           for x,y in zip(gf.grid_x,gf.grid_y)]
    poly=gpd.GeoDataFrame({'grid_id':gf.grid_id.astype(str).values},
                          geometry=boxes,crs='EPSG:6933')
    with rasterio.open(src) as ds:
        if ds.crs is None:raise ValueError('Native raster CRS missing')
        polygons=poly.to_crs(ds.crs)
        op=['mean','count'] if p['kind']=='mean' else ['sum','count']
        tab=exact_extract(src,polygons,op,include_cols=['grid_id'],output='pandas')
        if tab.grid_id.duplicated().any():raise ValueError('Native source exactextract duplicated grid')
        original=tab[['grid_id',op[0],'count']].copy()
        if p['kind']=='pixel_m2':original['reference']=original['sum']/1_000_000
        elif p['kind']=='pixel_count':original['reference']=original['sum']
        else:original['reference']=original['mean']
    fast=pd.read_parquet(fast_tile)
    compare=gf[['grid_id','land_area_km2']].merge(original[['grid_id','reference','count']],on='grid_id',how='left').merge(
        fast[['grid_id',p['column']]],on='grid_id',how='left')
    a=pd.to_numeric(compare['reference'],errors='coerce')
    b=pd.to_numeric(compare[p['column']],errors='coerce')
    valid=a.notna()&b.notna()
    d=(a-b).abs()
    qc={'status':'EXACT_AUDIT_DIAGNOSTIC_NOT_GLOBAL_PUBLICATION_GATE',
        'n':int(len(compare)),'n_valid':int(valid.sum()),
        'median_abs_difference':float(d[valid].median()) if valid.any() else None,
        'p95_abs_difference':float(d[valid].quantile(.95)) if valid.any() else None,
        'max_abs_difference':float(d[valid].max()) if valid.any() else None,
        'reference':'C++ exactextract native pixel area intersection in SOURCE CRS',
        'source_crs':str(ds.crs),'fast_method':'GDAL approximate 1km aligned resampling',
        'limitation':'Geographic CRS polygon/source-pixel coverage proportions are not true equal-area weights',
        'passed_publication_accuracy':False}
    out=Path(out)
    if out.exists():raise FileExistsError('Use fresh versioned comparison output')
    out.parent.mkdir(parents=True,exist_ok=True)
    compare.to_csv(out,index=False,encoding='utf-8-sig')
    json_write(out.with_suffix('.qc.json'),qc)
    return qc
