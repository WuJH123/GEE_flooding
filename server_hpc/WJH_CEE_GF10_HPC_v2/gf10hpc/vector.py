"""Massive GF10 centroid point assignments for geoBoundaries/UCDB/HydroATLAS.

Centre-in-polygon is an explicit PROXY; tiny/coastal cells may have centre at
sea. Never claim a dominant area overlay or hydraulic flow accumulation.
"""
from __future__ import annotations
from pathlib import Path
import os
import numpy as np
import pandas as pd
from shapely import points
from pyproj import Transformer
from .core import grid_indices, json_write

def assign(grid,src,out,field,layer=None,extra=(),batch=100_000,subset=False):
    import geopandas as gpd
    if not 1000<=batch<=300_000:raise ValueError('Batch 1k..300k')
    if not Path(src).exists():raise FileNotFoundError(src)
    boundary=gpd.read_file(src,layer=layer,engine='pyogrio')
    if boundary.crs is None:raise ValueError('Administrative/city basin CRS unknown')
    required=[field]+list(extra)
    if any(c not in boundary.columns for c in required):
        raise ValueError('Fields not found: '+str([x for x in required if x not in boundary]))
    if len(boundary)>100_000:
        raise ValueError('Too many polygons for one pass; choose hydro level<=8 and spatially chunk input')
    boundary=boundary[required+['geometry']].copy().to_crs('EPSG:6933')
    boundary=boundary.loc[boundary.geometry.notna()&~boundary.geometry.is_empty].reset_index(drop=True)
    # Expose original authority column without coercing IDs to floating point.
    g=grid_indices(pd.read_parquet(grid))
    if not subset and len(g)!=1_395_471:
        raise ValueError('Global GF10 expected, pass --pilot for synthetic subset')
    out=Path(out)
    if out.exists():raise FileExistsError('Use immutable versioned vector output: '+str(out))
    out.parent.mkdir(parents=True,exist_ok=True)
    frames=[]
    for start in range(0,len(g),batch):
        chunk=g.iloc[start:start+batch]
        x=(chunk.grid_x.to_numpy()+.5)*10000
        y=(chunk.grid_y.to_numpy()+.5)*10000
        one=gpd.GeoDataFrame({'grid_id':chunk.grid_id.to_numpy()},
              geometry=gpd.GeoSeries(points(x,y),crs='EPSG:6933'),crs='EPSG:6933')
        joined=gpd.sjoin(one,boundary,how='left',predicate='within')
        # Avoid a Python loop over 1.4 million cells: one vectorised groupby.
        joined=joined.drop(columns=['geometry','index_right'],errors='ignore')
        valid=joined.loc[joined[field].notna()].copy()
        valid[field]=valid[field].astype(str)
        counts=valid.groupby('grid_id')[field].nunique(dropna=True).rename('n_matching_geometries')
        one=valid.drop_duplicates('grid_id').set_index('grid_id')[[field]+list(extra)]
        subset=pd.DataFrame({'grid_id':chunk.grid_id.to_numpy()}).set_index('grid_id')
        subset=subset.join(counts,how='left').join(one,how='left')
        subset['n_matching_geometries']=subset['n_matching_geometries'].fillna(0).astype('int16')
        subset['ambiguous_assignment']=subset.n_matching_geometries>1
        subset.loc[subset.ambiguous_assignment,[field]+list(extra)]=None
        rec=subset.reset_index()
        frames.append(rec)
        print(f'[vector] {min(start+batch,len(g))}/{len(g)} centres',flush=True)
    result=pd.concat(frames,ignore_index=True)
    if result.grid_id.duplicated().any() or len(result)!=len(g):raise ValueError('Vector join lost GF10 IDs')
    if (result.ambiguous_assignment).any():
        print('[vector] Warning: ambiguous overlapping polygons retained as null',flush=True)
    temp=out.with_suffix('.parquet.writing')
    result.to_parquet(temp,index=False,compression='zstd');os.replace(temp,out)
    json_write(out.with_suffix('.qc.json'),{
      'status':'CENTROID_POLYGON_PROXY_NEEDS_COASTAL_AREA_VALIDATION',
      'n':len(result),'n_assigned':int(result[field].notna().sum()),
      'n_ambiguous':int(result.ambiguous_assignment.sum()),
      'source':str(src),'layer':layer,'field':field,
      'centroid_not_dominant_area':True,'publication_ready':False})
    return {'rows':len(result),'assigned':int(result[field].notna().sum())}
