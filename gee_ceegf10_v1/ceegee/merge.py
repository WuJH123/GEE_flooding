"""Join GEE GeoTIFF exports back to frozen GF10 by the exact EPSG6933 cell lattice.

No interpolation, no regridding, and no artificial zeros for uncovered pixels.
"""
from __future__ import annotations
import hashlib, json, pathlib
from .grid import load_grid

MERIT_BANDS=['merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2',
             'merit_permanent_water_fraction','merit_valid_fraction','merit_upa_max_km2']
WORLDCOVER_CODES=(10,20,30,40,50,60,70,80,90,95,100)
WORLDCOVER_BANDS=[f'wc_{c}_fraction_fullcell' for c in WORLDCOVER_CODES]+['wc_valid_fraction_fullcell']


def _read_band_values(ds, gx, gy, bands, result, seen, idx):
    import numpy as np
    t=ds.transform
    if ds.crs is None or ds.crs.to_epsg()!=6933:
        raise ValueError('GeoTIFF does not use frozen EPSG6933')
    if abs(t.a-10000)>0.001 or abs(t.e+10000)>0.001 or abs(t.b)>0.00001 or abs(t.d)>0.00001:
        raise ValueError('Source raster pixel grid is not 10km north-up')
    if abs(t.c/10000-round(t.c/10000))>1e-7 or abs(t.f/10000-round(t.f/10000))>1e-7:
        raise ValueError('Pixel grid not aligned to origin (0,0)')
    if ds.count!=len(bands):
        raise ValueError(f'Expected {len(bands)} ordered bands but TIFF has {ds.count}')
    listed=[s for s in ds.descriptions if s]
    if listed and len(listed)==len(bands) and list(listed)!=list(bands):
        raise ValueError('Band names/order differ from source contract; refusing blind column rename: '+str(listed))
    # One 10km cell pixel per original exact GF10 10km integer index.
    c0=round(t.c/10000);r0=round(t.f/10000)
    cols=gx+0-c0
    rows=r0-gy-1
    match=(cols>=0)&(cols<ds.width)&(rows>=0)&(rows<ds.height)
    ix=idx[match]
    if (seen[ix]>0).any():raise ValueError('Two exported GeoTIFFs overlap frozen GF10 cells')
    if len(ix)==0:return 0
    data=ds.read(masked=True).filled(np.nan).astype('float32')
    for j,band in enumerate(bands):
        result[band][ix]=data[j,rows[match],cols[match]]
    seen[ix]+=1
    return len(ix)


def join_exports(grid_path,tif_dir,family,out_path,expected_strips=12):
    import numpy as np
    import pandas as pd
    import rasterio
    fam={'merit':MERIT_BANDS,'worldcover':WORLDCOVER_BANDS}
    if family not in fam:raise ValueError('Unknown static GEE family')
    bands=fam[family]
    g=load_grid(grid_path)
    names=sorted(pathlib.Path(tif_dir).glob(f'full_{family}_strip_*.tif'))
    if len(names)!=expected_strips:
        raise ValueError(f'Expected {expected_strips} GeoTIFF stripes for {family}, found {len(names)}. Do not publish a partial global table')
    result={b:np.full(len(g),np.nan,dtype='float32') for b in bands}
    seen=np.zeros(len(g),dtype='uint8')
    gx=g.grid_x.to_numpy(dtype='int64');gy=g.grid_y.to_numpy(dtype='int64');idx=np.arange(len(g))
    source=[]
    for p in names:
        with rasterio.open(p) as ds:
            n=_read_band_values(ds,gx,gy,bands,result,seen,idx)
            source.append({'path':str(p),'size_bytes':p.stat().st_size,'GF10_in_tif':n})
    if np.any(seen!=1):
        raise ValueError(f'{int(np.sum(seen!=1))} frozen GF10 cells not represented exactly once in exported strip footprints')
    data=g[['grid_id','land_area_km2']].copy()
    for b,v in result.items():data[b]=v
    # Distinguish truly empty observation from zero; no filling of missing.
    if family=='worldcover':
        v=data['wc_valid_fraction_fullcell'].to_numpy()
        total=sum(data[b].fillna(0).to_numpy() for b in bands[:-1])
        good=np.isfinite(v)
        if np.any((total[good]<-0.02)|(total[good]>v[good]+0.035)):
            raise ValueError('WorldCover class area conservation out of bounds')
        if np.nanmax(v)>1.025 or np.nanmin(v)<-0.025:raise ValueError('Invalid coverage fraction')
    else:
        if np.nanmax(data['merit_permanent_water_fraction'].to_numpy())>1.025:
            raise ValueError('MERIT water fraction exceeds 1')
    out=pathlib.Path(out_path)
    if out.exists():raise FileExistsError('Refuse to overwrite immutable GF10 export: '+str(out))
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.parquet.writing')
    data.to_parquet(tmp,index=False,compression='zstd')
    tmp.replace(out)
    qc={'status':'GF10_GEE_GLOBAL_10KM_JOIN_COMPLETE_REQUIRES_COAST_QA',
        'family':family,'n_cells':len(data),'gf10_unique_id':not data.grid_id.duplicated().any(),
        'all_export_footprints_cover_grid':True,'source_tifs':source,
        'valid_cells':{b:int(data[b].notna().sum()) for b in bands},
        'not_land_clipped':True,'not_independent_physical_validation':True,
        'interpretation':'Native source aggregated and aligned at 10km; no increase in true native resolution'}
    out.with_suffix('.qc.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return qc
