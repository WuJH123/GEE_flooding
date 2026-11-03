"""Strict, full global GF10 per-tile wide static table, all available sources.

No annual climate, news observations, or native city-level data masquerading
as a measured daily/static cell. Separate annual/source tables kept outside.
"""
from __future__ import annotations
from pathlib import Path
import os
import pandas as pd
import numpy as np
from .shared import prepare_directory,read_json,write_json,file_identity
from ceeall.raster import candidates

FAMILIES={'gmted':5,'worldclim-bio':19,'worldclim-monthly':84,'grip-density':1}
VECTORS=('admin0','admin1','ucdb','basin','river','roads')
GHSL=('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020')


def _load_native_ghsl(root,family):
    parent=root/'data/derived'/f'hpc_exact_{family}_v2/tiles'
    files=sorted(parent.glob('tile_*.parquet'))
    if len(files)!=715:raise ValueError('GHSL 715 native tile products not all available: '+family)
    frame=pd.concat((pd.read_parquet(p) for p in files),ignore_index=True)
    if len(frame)!=1_395_471 or frame.grid_id.duplicated().any():
        raise ValueError('Original GHSL must have precisely 1,395,471 unique global IDs: '+family)
    if 'land_area_km2' in frame:frame=frame.drop(columns=['land_area_km2'])
    return frame.set_index('grid_id',verify_integrity=True)

def _check_complete(root):
    products=[];paths=[]
    for family,n in FAMILIES.items():
        c=candidates(root,family)
        if len(c)!=n:raise ValueError(f'{family} expected {n} original product TIFFs; discovered {len(c)}')
        for source in c:
            product=root/'data/derived/cee_all_v11'/family/source.stem
            qc=product/'run_qc.json'
            if not qc.is_file():raise FileNotFoundError('Missing global raster source '+str(source))
            z=read_json(qc)
            if z.get('status')!='FULL_TILES_NATIVE_EXACT_NEEDS_LAND_QA' or z.get('n_rows')!=1_395_471 or z.get('n_tasks')!=715:
                raise ValueError(f'{family} not FULL global 715 partitions: '+str(qc))
            if len(list((product/'tiles').glob('tile_*.parquet')))!=715:
                raise ValueError('Raster source has incomplete tile files: '+str(product))
            products.append((family,source,product))
            paths.append(file_identity(qc))
    for family in GHSL:
        qc=root/'data/derived'/f'hpc_exact_{family}_v2/run_qc.json'
        if not qc.exists():raise FileNotFoundError(qc)
        z=read_json(qc)
        if z.get('n_tasks')!=715:raise ValueError('Original GHSL is not global '+family)
        paths.append(file_identity(qc))
    for family in VECTORS:
        q=root/'data/derived/cee_all_global_v2/vector'/family/'run_qc.json'
        if not q.is_file():raise FileNotFoundError(q)
        z=read_json(q)
        if z.get('n_grid')!=1_395_471 or z.get('n_tiles')!=715:
            raise ValueError('Vector source not all GF10 '+family)
        paths.append(file_identity(q))
    gis=root/'data/derived/cee_all_global_v2/gisd30_history'
    if not (gis/'run_qc.json').is_file():raise FileNotFoundError('GISD30 history missing')
    return products,paths

def run(root):
    root=Path(root)
    products,paths=_check_complete(root)
    grid=root/'data/working/cee_all_tiles64_v11/tiles'
    tiles=sorted(grid.glob('tile_*.parquet'))
    if len(tiles)!=715:raise ValueError('Frozen grid tile index has not been built')
    dest,jid=prepare_directory(root/'data/derived/cee_all_global_v2/gf10_static_wide',
       {'frozen':file_identity(root/'gf10_global_nonantarctic_land.parquet'),
        'sources':paths,'algorithm':'per_gridtile_join_all_valid_static_sources_v2'})
    print('[static merge] Loading five original global GHSL sources and GISD30 sparse history...',flush=True)
    ghsl=[(family,_load_native_ghsl(root,family)) for family in GHSL]
    gisd_file=root/'data/derived/cee_all_global_v2/gisd30_history/gf10_gisd30_history_1985_2020.parquet'
    hist=pd.read_parquet(gisd_file)
    if hist.grid_id.duplicated().any():raise ValueError('GISD history duplicated GF10')
    gisd=hist.set_index('grid_id',verify_integrity=True)
    if any(k not in gisd.columns for k in ('gisd_impervious_frac_2000_valid_source','gisd_impervious_frac_2020_valid_source')):
        raise ValueError('GISD historical fraction metrics missing')
    yearcols=[x for x in gisd.columns if x.startswith('gisd_impervious_frac_') or x=='source_tile_seam_possible_duplicate']
    qcsummary=[]
    for i,tile in enumerate(tiles,1):
        out=dest/'tiles'/tile.name;qc=out.with_suffix('.qc.json')
        if out.exists() and qc.exists():
            z=read_json(qc)
            if z.get('job_id')!=jid or z.get('status')!='OK':raise ValueError('Existing wide tile QC differs: '+str(out))
            import pyarrow.parquet as pq
            if pq.ParquetFile(out).metadata.num_rows!=z['rows']:
                raise ValueError('Wide tile Parquet not complete '+str(out))
            qcsummary.append(z);continue
        if out.exists() or qc.exists():raise FileExistsError('Partial source wide output '+str(out))
        frame=pd.read_parquet(tile,columns=['grid_id','grid_x','grid_y','land_area_km2']).set_index('grid_id')
        for family,data in ghsl:
            add=data.reindex(frame.index)
            overlap=(set(frame.columns)&set(add.columns))
            if overlap:raise ValueError('GHSL conflicting source columns '+str(overlap))
            frame=frame.join(add,how='left')
        frame=frame.join(gisd.reindex(frame.index)[yearcols],how='left')
        for family,source,product in products:
            p=product/'tiles'/tile.name
            if not p.is_file():raise FileNotFoundError('Raster tile missing '+str(p))
            sub=pd.read_parquet(p).set_index('grid_id')
            drop=['grid_x','grid_y','land_area_km2']
            sub=sub.drop(columns=[k for k in drop if k in sub],errors='ignore')
            shared=set(sub.columns)&set(frame.columns)
            if shared:raise ValueError(f'Source field collision {source}: {shared}')
            frame=frame.join(sub,how='left')
        for family in VECTORS:
            p=root/'data/derived/cee_all_global_v2/vector'/family/'tiles'/tile.name
            if not p.exists():raise FileNotFoundError('Vector tile missing '+str(p))
            sub=pd.read_parquet(p).set_index('grid_id')
            shared=set(sub.columns)&set(frame.columns)
            if shared:raise ValueError('Vector field collision '+str(shared))
            frame=frame.join(sub,how='left')
        if len(frame)!=len(pd.read_parquet(tile,columns=['grid_id'])):
            raise ValueError('Global GF10 row conservation failed merging '+str(tile))
        if frame.index.has_duplicates:raise ValueError('Duplicate GF10 IDs')
        frame=frame.reset_index()
        out.parent.mkdir(parents=True,exist_ok=True)
        temp=out.with_suffix('.writing.parquet');frame.to_parquet(temp,index=False,compression='zstd');os.replace(temp,out)
        z={'status':'OK','job_id':jid,'rows':len(frame),'n_columns':len(frame.columns),
           'not_land_polygon_clipped':True,'publication_ready':False}
        write_json(qc,z);qcsummary.append(z)
        if i%20==0 or i==len(tiles):print(f'[static merge] {i}/715 tiles, {len(frame.columns)} indicator/source fields',flush=True)
    if sum(x['rows'] for x in qcsummary)!=1_395_471:
        raise ValueError('Global wide GF10 row conservation failed')
    qc={'status':'FULL_GLOBAL_STATIC_WIDE_WITH_PROVENANCE_NEEDS_SOURCE_LAND_QA',
         'n_tiles':715,'n_grid':1_395_471,'n_columns':qcsummary[0]['n_columns'],
         'n_raster_products':len(products)+len(GHSL),'n_vector_products':len(VECTORS),
         'annual_climate_not_mixed':True,'flood_news_not_mixed':True,
         'land_polygon_clipped':False,'publication_ready':False}
    write_json(dest/'run_qc.json',qc)
    return qc
