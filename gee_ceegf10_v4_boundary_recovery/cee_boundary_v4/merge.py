"""Join QA-passed V4 boundary CSV and normal 10x10 GeoTIFF to GF10.

Incomplete cloud processing remains an explicitly partial product.
No invalid V3 image may enter the publication table.
"""
from __future__ import annotations
import argparse,pathlib,json,numpy as np
from . import core,audit

def merge(out=None):
    import pandas as pd
    import rasterio
    from ceeprodgee import contract
    from .cli import ROOT,REG,frozen
    base,config,g,model,ct=frozen()
    entries=core.load(REG,[])
    if not entries:raise ValueError('No V4 export tasks')
    metrics=list(contract.MERIT_BANDS)
    indexed=g[['grid_id','grid_x','grid_y','land_area_km2']].copy().set_index('grid_id',verify_integrity=True)
    values=pd.DataFrame(index=indexed.index,columns=metrics,dtype=float)
    source=pd.Series(pd.NA,index=indexed.index,dtype='string')
    counts={'point_table_tiles':0,'raster_tiles':0,'land_grid_with_valid_hand':0}
    visited=set()
    for rec in entries:
        if not rec.get('local_qc_pass') or rec.get('pilot'):
            continue
        tile=core.Tile(*[int(z) for z in rec['key'].split('_')[1:]])
        fp=ROOT/'downloads'/rec['file']
        if not fp.is_file():raise FileNotFoundError('Previously validated source file missing '+str(fp))
        expected=core.expected_ids(g,tile)
        if visited.intersection(expected):raise ValueError('Global tile overlap; duplicated frozen GF10 ID')
        if rec['mode']=='POINT_TABLE':
            audit.audit_boundary_csv(fp,g,tile,metrics)
            df=pd.read_csv(fp,dtype={'grid_id':'string'}).set_index('grid_id',verify_integrity=True)
            sub=df[metrics].apply(pd.to_numeric,errors='coerce')
            counts['point_table_tiles']+=1
        else:
            audit.audit_regular_raster(fp,g,tile,metrics)
            with rasterio.open(fp) as ds:z=ds.read(masked=True).filled(np.nan)
            points=[]
            for yy in range(tile.n):
                for xx in range(tile.n):
                    k=f'{tile.x+xx}_{tile.y+tile.n-1-yy}'
                    if k in expected:points.append((k,z[:,yy,xx].tolist()))
            sub=pd.DataFrame([p[1] for p in points],index=[p[0] for p in points],columns=metrics,dtype=float)
            counts['raster_tiles']+=1
        if set(sub.index)!=expected:raise ValueError('Final tile ID reconciliation failed')
        values.loc[sub.index,metrics]=sub[metrics]
        source.loc[sub.index]=rec['key']
        visited|=expected
    outp=pathlib.Path(out or ROOT/'data'/'GF10_merit_v4_verified_partial.parquet')
    if outp.exists():raise FileExistsError('Refuse overwrite of frozen GF10 derived product '+str(outp))
    outp.parent.mkdir(parents=True,exist_ok=True)
    final=indexed.join(values).reset_index()
    final['source_task_key']=source.reindex(final.grid_id).to_numpy()
    final.to_parquet(outp,index=False,compression='zstd')
    counts.update({'status':'PARTIAL_NOT_ALL_GLOBAL' if len(visited)!=len(g) else 'ALL_REGISTERED_GF10_TILES_QC_PASS',
                   'grid_count':len(g),'n_cells_registered':len(visited),
                   'n_missing_cells':len(g)-len(visited),
                   'land_grid_with_valid_hand':int(final[metrics[0]].notna().sum()),
                   'output':str(outp),'methods':'V4 projected 10km native raster + boundary GF10 point table; no V3 rejected outputs',
                   'not_real_flood_validation':True})
    core.atomic_json(outp.with_suffix('.qc.json'),counts)
    return counts

def main():
    p=argparse.ArgumentParser();p.add_argument('--out')
    args=p.parse_args();print(json.dumps(merge(args.out),indent=2))
if __name__=='__main__':main()
