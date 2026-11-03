"""Join ONLY audited, completed static GF10 products. Annual data kept apart."""
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd
import numpy as np
from .core import grid_indices,read_json,json_write

def assemble(grid,products,out,allow_pilot=False):
    g=grid_indices(pd.read_parquet(grid))
    if not allow_pilot and len(g)!=1_395_471:
        raise ValueError('Frozen global GF10 count mismatch')
    keep=['grid_id','land_area_km2']
    if 'land_fraction' in g:keep.append('land_fraction')
    result=g[keep].copy()
    n=len(result)
    if result.grid_id.duplicated().any():raise ValueError('GF10 duplicate ID')
    result=result.set_index('grid_id',verify_integrity=True)
    metadata=[]
    for product in products:
        source=Path(product)
        qcfile=source/'run_qc.json'
        if not qcfile.is_file():raise FileNotFoundError('Missing finished raster job QA: '+str(source))
        qa=read_json(qcfile)
        if qa.get('status') not in ('ALL_TILES_FAST_APPROX_NEEDS_EXACT_AND_COAST_QA','ALL_TILES_NATIVE_EXACT_NEEDS_COAST_QA') and not allow_pilot:
            raise ValueError('Partial/ineligible raster product '+str(source))
        tiles=sorted((source/'tiles').glob('tile_*.parquet'))
        if len(tiles)!=qa['n_tasks']:
            raise ValueError(f'Incomplete produced tiles {len(tiles)} vs {qa["n_tasks"]}: '+str(source))
        frame=pd.concat((pd.read_parquet(z) for z in tiles),ignore_index=True)
        if frame.grid_id.duplicated().any():raise ValueError('Duplicate grid in '+str(source))
        if not allow_pilot and len(frame)!=n:raise ValueError('Product lacks some GF10 IDs '+str(source))
        frame=frame.set_index('grid_id',verify_integrity=True)
        all_cols=set(frame)-{'land_area_km2'}
        overlaps=all_cols & set(result)
        if overlaps:raise ValueError(f'Static source column collision {overlaps}; give new versioned source name')
        if result.index.get_indexer(frame.index).min(initial=0)<0:raise ValueError('Product contains unknown grid ID')
        result=result.join(frame[list(all_cols)],how='left',validate='one_to_one')
        metadata.append({'product':str(source),'profile':qa['profile'],
             'source_epoch':qa['source_epoch'],'source_family':qa['native_source'],
             'extraction_method':qa['method'],'n_valid':qa.get('valid_rows',0)})
    # Important cross-product invariants: enforce fail-closed science QC
    if {'built_area_km2_2000','built_area_km2_2020'}<=set(result):
        old=result.built_area_km2_2000
        new=result.built_area_km2_2020
        if ((old-new)>5.0).sum()>n*.001:
            raise ValueError('Too many implausible built-area decreases; compare original GHSL versions')
        result['built_growth_km2_2000_2020']=new-old
        result['built_growth_fraction_full_cell_2000_2020']=(new-old)/100
    if {'built_nres_area_km2_2020','built_area_km2_2020'}<=set(result):
        m=result[['built_nres_area_km2_2020','built_area_km2_2020']].dropna()
        if (m.built_nres_area_km2_2020>m.built_area_km2_2020+.5).any():
            raise ValueError('Nonresidential built area exceeds total built area; fail closed')
    out=Path(out)
    if out.exists():raise FileExistsError('Versioned wide output exists; never overwrite '+str(out))
    out.parent.mkdir(parents=True,exist_ok=True)
    temp=out.with_suffix('.writing.parquet')
    result.reset_index().to_parquet(temp,index=False,compression='zstd')
    os.replace(temp,out)
    qc={'status':'STATIC_APPROX_NEEDS_EXACT_SOURCE_AND_LAND_QA',
        'n':n,'inputs':metadata,'valid_n':{k:int(result[k].notna().sum())
          for k in result if not k.endswith(('_flag','_fraction')) and k!='land_area_km2'},
        'annual_weather_mixed':False,'news_outcome_mixed':False,
        'native_exact_area_proven':False,'land_polygon_clipped':False,
        'publication_ready':False}
    json_write(out.with_suffix('.qc.json'),qc)
    return {'rows':n,'columns':len(result.columns)+1,'qc':str(out.with_suffix('.qc.json'))}
