"""Local frozen GF10 audit for bounded boundary-point table and ordinary raster.

The table source must be a newly completed GEE export with exactly one
GF10 grid ID per row, 16 frozen M1 indicator columns and no duplicate cells.
Missing hydrologic coverage is represented with NaN, not 0 or pseudo-controls.
"""
from __future__ import annotations
import pathlib, math, json
import numpy as np
from .core import Tile,expected_ids,atomic_json


def audit_boundary_csv(path,grid,tile,bands,expected_mode='POINT_TABLE'):
    import pandas as pd
    p=pathlib.Path(path)
    if p.suffix.lower()!='.csv':raise ValueError('Must read exported GEE Table CSV, not a failed raster')
    df=pd.read_csv(p,dtype={'grid_id':'string'})
    need={'grid_id','grid_x','grid_y'}|set(bands)
    if not need.issubset(df.columns):raise ValueError('GEE CSV missing columns: '+','.join(sorted(need-set(df.columns))))
    if df.grid_id.isna().any() or df.grid_id.duplicated().any():raise ValueError('No duplicate/missing grid_id allowed')
    expected=expected_ids(grid,tile)
    if set(df.grid_id)!=expected:
        raise ValueError(f'Export membership mismatch; expected {len(expected)} GF10 IDs, got {len(df)}, missing={list(expected-set(df.grid_id))[:4]}')
    if not all((df.grid_x.astype(int).astype(str)+'_'+df.grid_y.astype(int).astype(str))==df.grid_id):raise ValueError('Source CSV x/y disagrees with grid_id')
    for b in bands:
        df[b]=pd.to_numeric(df[b],errors='coerce')
        if np.isinf(df[b].to_numpy(dtype='float64')).any():raise ValueError('Inf source indicator: '+b)
    # Missing pixels are tolerated and audited. 0 must never be filled for missing.
    idx={k:k for k in bands}
    for b in bands:
        if 'fraction' in b:
            v=df[b].dropna()
            if not v.between(-1e-5,1.00001).all():raise ValueError('Fraction outside [0,1]: '+b)
    for values in [('merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid','merit_hand_le10_fraction_valid'),('merit_hand_p10_m','merit_hand_p50_m','merit_hand_p90_m')]:
        vals=df[list(values)].dropna()
        if not ((vals[values[0]]<=vals[values[1]]+1e-3)&(vals[values[1]]<=vals[values[2]]+1e-3)).all():raise ValueError('HAND monotonicity')
    if {'merit_upa_max_km2','merit_upa_max_log1p'}.issubset(df.columns):
        z=df[['merit_upa_max_km2','merit_upa_max_log1p']].dropna()
        if not np.allclose(np.log1p(z.merit_upa_max_km2),z.merit_upa_max_log1p,atol=0.003):raise ValueError('UPA log1p')
    return {'status':'PASS_TABLE_GF10_SCHEMA_AND_MEMBERSHIP','source':str(p),'tile_key':tile.key,
            'method':expected_mode,'n_expected':len(expected),'n_rows':len(df),
            'n_hand_valid':int(df[bands[0]].notna().sum()),'missing_per_band':df[list(bands)].isna().sum().astype(int).to_dict(),
            'not_independent_flood_validation':True}

def audit_regular_raster(path,grid,tile,bands):
    import rasterio
    from rasterio.transform import Affine
    from ceeprodgee.qc import check_raster
    report=check_raster(path,'merit',tile.x,tile.y,tile.n,expected_manifest=tuple(bands))
    with rasterio.open(path) as ds:
        expected=Affine(*tile.transform)
        if not ds.transform.almost_equals(expected,precision=1e-7):raise ValueError('Tile raster transform differs from frozen 10km lattice')
        a=ds.read(masked=True).filled(np.nan)
    actual=expected_ids(grid,tile)
    valid=0
    for y in range(tile.n):
        for x in range(tile.n):
            gx=tile.x+x;gy=tile.y+tile.n-y-1
            if f'{gx}_{gy}' in actual and np.isfinite(a[0,y,x]):valid+=1
    report.update({'status':'PASS_RASTER_GRID_AFFINE_AND_VALUES','n_land_expected':len(actual),'land_valid':valid})
    return report
