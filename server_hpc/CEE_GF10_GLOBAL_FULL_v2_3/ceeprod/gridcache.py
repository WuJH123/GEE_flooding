"""Cache full EPSG6933 GF10 polygons projected once into EPSG4326.

Caching is an exact geometry optimization, not a pixel-resolution change.
"""
from __future__ import annotations
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import os
from .shared import write_json,read_json

def _one(task):
    source,cache=task
    import pandas as pd
    import geopandas as gpd
    from ceeall.raster import _build_polygons
    src=Path(source);out=Path(cache)
    if out.exists():
        prior=gpd.read_parquet(out)
        if len(prior)!=len(pd.read_parquet(src,columns=['grid_id'])):
            raise ValueError('Geometry cache and frozen tile disagree: '+str(out))
        return ('REUSED',len(prior))
    tile=pd.read_parquet(src)
    geo=_build_polygons(tile,'EPSG:4326')
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.writing.parquet')
    geo.to_parquet(tmp,index=False,compression='zstd');os.replace(tmp,out)
    return ('WROTE',len(tile))

def prepare(root,workers=12):
    root=Path(root);tiles=sorted((root/'data/working/cee_all_tiles64_v11/tiles').glob('tile_*.parquet'))
    if len(tiles)!=715:raise ValueError('Expected 715 frozen GF10 tiles, got '+str(len(tiles)))
    dest=root/'data/working/cee_geo4326_v2'
    tasks=[(str(p),str(dest/p.name)) for p in tiles]
    written=reused=rows=0
    with ProcessPoolExecutor(max_workers=min(workers,32)) as pool:
        futures=[pool.submit(_one,t) for t in tasks]
        for i,f in enumerate(as_completed(futures),1):
            st,n=f.result(); rows+=n
            if st=='WROTE':written+=1
            else:reused+=1
            if i%50==0:print(f'[geometry-cache] {i}/715, written={written}, reused={reused}',flush=True)
    if rows!=1_395_471:raise ValueError('Global cached geometry lost IDs')
    qc={'status':'ALL_GLOBAL_GF10_GEOMETRIES_CACHED','n_tiles':715,'n_cells':rows,'written':written,'reused':reused,
        'geometry':'densified_2km_then_EPSG4326','antimeridian_unsupported_marked_null':True}
    write_json(dest/'cache_qc.json',qc)
    return qc
