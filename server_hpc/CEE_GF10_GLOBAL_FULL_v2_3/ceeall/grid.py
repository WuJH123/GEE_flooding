"""Create reusable global GF10 64-cell-square spatial shards without source modification."""
from pathlib import Path
from .common import verify_frozen_grid,ensure_job,atomic_json,atomic_parquet,read_json

def tiles(root,strict=True,tile_side=64):
    import numpy as np
    import pandas as pd
    root=Path(root)
    g,meta=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',strict)
    if tile_side!=64:raise ValueError('Published server workflow uses tile_side=64')
    dest=root/'data/working/cee_all_tiles64_v11'
    j=ensure_job(dest,{'grid_identity':meta['source'],'tile_side':tile_side,'version':3})
    g['tile_ix']=(g.grid_x//64).astype('int32');g['tile_iy']=(g.grid_y//64).astype('int32')
    n=0
    for (x,y),d in g.groupby(['tile_ix','tile_iy'],sort=True):
        p=dest/'tiles'/f'tile_{x}_{y}.parquet'
        if p.exists():
            old=pd.read_parquet(p,columns=['grid_id'])
            if len(old)!=len(d) or set(old.grid_id)!=set(d.grid_id):raise ValueError('Existing shard differs '+str(p))
        else:atomic_parquet(d[['grid_id','grid_x','grid_y','land_area_km2']],p)
        n+=1
    atomic_json(dest/'tiles_qc.json',{'n_tiles':n,**meta,'job_id':j,'status':'GF10_TILES_READY'})
    return {'n_tiles':n,'path':str(dest),'n_cells':len(g)}
