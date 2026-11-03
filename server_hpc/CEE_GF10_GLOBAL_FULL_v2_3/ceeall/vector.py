"""Inspect and link administrative, city and basin features without pretending centroid lookup is area overlap."""
from __future__ import annotations
from pathlib import Path
from .common import atomic_parquet,atomic_json,verify_frozen_grid,ensure_job,fidentity

def inspect(path):
    import pyogrio
    p=Path(path)
    if not p.exists():raise FileNotFoundError(path)
    frames=pyogrio.list_layers(p)
    report=[]
    for layer,geom in frames:
        info=pyogrio.read_info(p,layer=layer)
        report.append({'layer':str(layer),'geometry_type':str(geom),
            'n_features':info.get('features'), 'crs':str(info.get('crs')),
            'fields':[str(x) for x in info.get('fields',[])]})
    return report

def centroid_link(root,source,layer,fields,tag,max_cells=None):
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import Point
    root=Path(root);source=Path(source)
    if not source.exists():raise FileNotFoundError(source)
    grid,grid_qc=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',max_cells is None)
    if max_cells:grid=grid.head(max_cells).copy()
    fields=[x.strip() for x in fields if x.strip()]
    if not fields:raise ValueError('At least one source field required')
    layers=inspect(source)
    desc=next((x for x in layers if x['layer']==layer),None)
    if not desc:raise ValueError('Layer missing '+layer)
    missing=set(fields)-set(desc['fields'])
    if missing:raise ValueError('Missing source fields: '+str(sorted(missing)))
    shapes=gpd.read_file(source,layer=layer,columns=fields)
    if not shapes.crs:raise ValueError('Source has no CRS')
    if shapes.geometry.isna().all():raise ValueError('Source has no geometry')
    points=gpd.GeoDataFrame({'grid_id':grid.grid_id},geometry=gpd.points_from_xy(
       (grid.grid_x+0.5)*10000,(grid.grid_y+0.5)*10000),crs='EPSG:6933')
    points=points.to_crs(shapes.crs)
    matches=gpd.sjoin(points,shapes,predicate='within',how='left')
    dup=matches.grid_id.duplicated(keep=False)
    # IMPORTANT: multiple polygons at one point are ambiguous and not silently resolved.
    ambig=set(matches.loc[dup,'grid_id'])
    out=matches[['grid_id',*fields]].copy()
    if ambig:out.loc[out.grid_id.isin(ambig),fields]=None
    out=out.drop_duplicates(subset='grid_id').reset_index(drop=True)
    if len(out)!=len(grid):raise ValueError('Output must have one row per GF10 cell')
    out['link_ambiguous']=out.grid_id.isin(ambig)
    dest=root/'data/derived/cee_all_v11/vector'/tag
    job=ensure_job(dest,{'source':fidentity(source),'layer':layer,'fields':fields,
                'grid':fidentity(root/'gf10_global_nonantarctic_land.parquet'),
                'max_cells':max_cells,'method':'centroid_within_v11'})
    file=dest/'link.parquet'
    if file.exists():
        raise FileExistsError('Existing vector output not overwritten '+str(file))
    atomic_parquet(out,file)
    atomic_json(dest/'link_qc.json',{'job_id':job,'n_grid':len(grid),'n_linked':int(out[fields[0]].notna().sum()),
             'n_ambiguous':len(ambig),'status':'CENTROID_PROXY_NOT_AREA_OVERLAP',
             'land_centroid_not_checked':True,'publication_ready':False})
    return {'n_grid':len(grid),'linked':int(out[fields[0]].notna().sum()),'ambiguous':len(ambig),'output':str(file)}
