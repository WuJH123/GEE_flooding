"""Assemble all 5x5 audited ESA COG local tiles into original frozen GF10 IDs.

Zero is never substituted for a missing source tile or missing land pixel.
"""
from __future__ import annotations
import argparse,pathlib,json,hashlib
import numpy as np
from . import grid,contract,qc
from .worldcover_derived import derive

def merge(grid_file,plan_file,tile_dir,out_file):
    import pandas as pd
    import rasterio
    base=grid.read_grid(grid_file,strict=True)
    plan=pd.read_csv(plan_file)
    if set(plan.family)!={'worldcover'} or not plan.tile_size.eq(5).all():raise ValueError('Invalid 5x5 WorldCover plan')
    if plan.tile_key.duplicated().any():raise ValueError('Duplicate tile in plan')
    locator={(int(x),int(y)):i for i,(x,y) in enumerate(zip(base.grid_x,base.grid_y))}
    raw=np.full((len(base),25),np.nan,dtype=np.float32)
    covered=np.zeros(len(base),dtype=bool)
    missing=[];count=0
    for r in plan.itertuples(index=False):
        x,y,n=int(r.tile_x0),int(r.tile_y0),int(r.tile_size)
        p=pathlib.Path(tile_dir)/f'wc_local_{x}_{y}_{n}.tif'
        if not p.is_file() or not p.with_suffix('.qc.json').exists():
            missing.append(str(p));continue
        qc.check_raster(p,'worldcover',x,y,n,expected_manifest=contract.WC_BANDS)
        with rasterio.open(p) as ds:arr=ds.read(masked=True).filled(np.nan)
        for row in range(n):
            for col in range(n):
                idx=locator.get((x+col,y+n-1-row))
                if idx is None:continue
                if covered[idx]:raise ValueError('GF10 overlap from multiple WorldCover tiles')
                raw[idx,:]=arr[:,row,col]
                covered[idx]=True;count+=1
    expected=int(plan.n_land_cells.sum())
    if missing or int(covered.sum())!=expected:
        raise ValueError(f'Incomplete source or duplicative GF10: missing tiles={len(missing)}, visited={covered.sum()}, expected={expected}; first={missing[:3]}')
    if expected!=len(base):
        raise ValueError('Global merge requires every frozen GF10 ID; study output must be separately versioned')
    result=base[['grid_id','grid_x','grid_y','land_area_km2']].copy()
    for k,name in enumerate(contract.WC_BANDS):result[name]=raw[:,k]
    result=derive(result)
    p=pathlib.Path(out_file)
    if p.exists():raise FileExistsError('Refusing to overwrite immutable global source product: '+str(p))
    p.parent.mkdir(parents=True,exist_ok=True)
    result.to_parquet(p,index=False,compression='zstd')
    report={'status':'GLOBAL_COMPLETE_STRUCTURAL_QA_NOT_INDEPENDENT_LABEL_ACCURACY',
      'n_gf10':len(result),'n_source_tiles':len(plan),
      'n_cells_visit_once':int(covered.sum()),
      'n_gf10_nonempty_esa':int(result.wc_valid_fraction_fullcell.gt(0).sum()),
      'n_very_small_land_cells':int(result.land_area_km2.lt(1).sum()),
      'lowland_tiny_island_warning':'Tiny islands may not appear in a 10m source pixel-centre rasterization',
      'land_fraction_vs_vector_source':'Independently validated per source 5x5 tile at <0.01 absolute area-fraction discrepancy',
      'not_flood_truth':True}
    p.with_suffix('.qc.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--grid',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--tiles',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(merge(a.grid,a.plan,a.tiles,a.out),indent=2))
if __name__=='__main__':main()
