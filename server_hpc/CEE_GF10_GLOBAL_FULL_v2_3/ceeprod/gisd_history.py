"""Native GISD30 impervious expansion at 8 source epochs, stream 5deg TIFFs.

No category-code averaging. Source geographic cells are categorical and
area-fraction weighting in a projected 10km full cell is an approximation if
native geographic-cell area varies, so remain explicitly QA-gated.
"""
from __future__ import annotations
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
from .shared import prepare_directory,read_json,write_json,file_identity
from ceeall.gisd import _gf10_source_overlap_mask
from ceeall.common import gf10_bounds

YEARS=[1985,1990,1995,2000,2005,2010,2015,2020]

def _source_one(task):
    src,gridfile,out,jid=task
    import rasterio,geopandas as gpd
    from rasterio.warp import transform_bounds
    from shapely import segmentize
    from shapely.geometry import box
    from exactextract import exact_extract
    src=Path(src);out=Path(out)
    dest=out/'parts'/f'{src.stem}.parquet';qc=dest.with_suffix('.qc.json')
    if dest.exists() and qc.exists():
        d=read_json(qc)
        if d.get('status')=='OK' and d.get('job_id')==jid and d.get('source')==file_identity(src):
            import pyarrow.parquet as pq
            if pq.ParquetFile(dest).metadata.num_rows==d['rows']:
                return {'status':'REUSED','rows':d['rows']}
        raise ValueError('GISD30 previous source output integrity mismatch '+str(dest))
    if dest.exists() or qc.exists():raise FileExistsError('Interrupted GISD30 output; do not destroy '+str(dest))
    g=pd.read_parquet(gridfile,columns=['grid_id','grid_x','grid_y'])
    with rasterio.open(src) as ds:
        if not ds.crs or not ds.crs.is_geographic or ds.count!=1:
            raise ValueError('Original GISD30 source expected geographic categorical TIFF')
        bounds=transform_bounds(ds.crs,'EPSG:6933',*ds.bounds,densify_pts=61)
        keep=_gf10_source_overlap_mask(g.grid_x.to_numpy(),g.grid_y.to_numpy(),bounds)
        g=g.loc[keep]
        if g.empty:
            outframe=pd.DataFrame({'grid_id':pd.Series(dtype=str),'native_valid_count':pd.Series(dtype=float),
                **{f'impervious_{y}_count':pd.Series(dtype=float) for y in YEARS}})
        else:
            poly=[segmentize(box(*gf10_bounds(x,y)),2000) for x,y in zip(g.grid_x,g.grid_y)]
            zones=gpd.GeoDataFrame({'grid_id':g.grid_id.to_numpy()},geometry=poly,crs='EPSG:6933').to_crs(ds.crs)
            bad=(zones.bounds.maxx-zones.bounds.minx)>5
            if bad.any():zones.loc[bad,'geometry']=None
            good=zones.geometry.notna()&~zones.geometry.is_empty
            if good.any():
                values=exact_extract(str(src),zones.loc[good],['count','unique','frac'],
                    include_cols=['grid_id'],output='pandas')
            else:values=pd.DataFrame(columns=['grid_id','count','unique','frac'])
            c=pd.to_numeric(values['count'],errors='coerce').to_numpy(dtype=float)
            records={'grid_id':values['grid_id'].to_numpy(),'native_valid_count':c}
            vals={year:np.full(len(c),np.nan,dtype=np.float64) for year in YEARS}
            for i,(codes,shares) in enumerate(zip(values['unique'],values['frac'])):
                if not np.isfinite(c[i]) or c[i]<=0:continue
                if codes is None or shares is None:raise ValueError('Invalid GISD categorical pair')
                codes=np.asarray(codes,dtype=int);shares=np.asarray(shares,dtype=float)
                if (len(codes)!=len(shares) or not np.isfinite(shares).all() or (shares<0).any()
                    or shares.sum()>1.001 or ((codes<0)|(codes>8)).any()):
                    raise ValueError('GISD30 class values unexpected: '+str(codes.tolist()))
                for j,year in enumerate(YEARS,1):
                    vals[year][i]=c[i]*shares[(codes>=1)&(codes<=j)].sum()
            for year in YEARS:records[f'impervious_{year}_count']=vals[year]
            outframe=pd.DataFrame(records).loc[lambda x:x.native_valid_count>0]
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix('.writing.parquet');outframe.to_parquet(tmp,index=False,compression='zstd');os.replace(tmp,dest)
    write_json(qc,{'status':'OK','job_id':jid,'source':file_identity(src),'rows':len(outframe),
      'periods':YEARS,'method':'original_30m_classes_unique_frac_angular_pixel_coverage',
      'not_land_polygon_clipped':True,'publication_ready':False})
    return {'status':'WROTE','rows':len(outframe)}

def _combine(root,source_files,out):
    results=[]
    import pyarrow.parquet as pq
    for p in source_files:
        q=p.with_suffix('.qc.json')
        if not q.is_file():raise FileNotFoundError('Missing GISD source QC: '+str(q))
        j=read_json(q)
        if j.get('status')!='OK' or pq.ParquetFile(p).metadata.num_rows!=j['rows']:
            raise ValueError('Invalid GISD original source part '+str(p))
        x=pd.read_parquet(p)
        if not x.empty:results.append(x)
    if not results:raise ValueError('GISD source tiles have zero valid classified cells')
    joined=pd.concat(results,ignore_index=True)
    sums={f'impervious_{y}_count':'sum' for y in YEARS}
    sums['native_valid_count']='sum'
    per=joined.groupby('grid_id',as_index=False).agg(sums)
    ntiles=joined.groupby('grid_id',sort=False).size().rename('n_source_tiles').reset_index()
    per=per.merge(ntiles,on='grid_id',validate='one_to_one')
    for year in YEARS:
        col=f'impervious_{year}_count'
        frac=f'gisd_impervious_frac_{year}_valid_source'
        per[frac]=per[col]/per.native_valid_count
        if not per[frac].dropna().between(-1e-6,1.00001).all():
            raise ValueError('GISD30 class fraction outside 0..1 for '+str(year))
    per['source_tile_seam_possible_duplicate']=per.n_source_tiles>1
    dest=out/'gf10_gisd30_history_1985_2020.parquet'
    if dest.exists():
        raise FileExistsError('Already assembled GISD30 history; use QC to reuse, or version output')
    temp=dest.with_suffix('.writing.parquet');per.to_parquet(temp,index=False,compression='zstd');os.replace(temp,dest)
    write_json(out/'combine_qc.json',{'status':'GISD30_HISTORY_COMBINED_NATIVE_CATEGORICAL_NEEDS_SEAM_AND_COAST_QA',
      'n_grid_with_coverage':len(per),'years':YEARS,
      'n_possible_source_seam_geometries':int(per.source_tile_seam_possible_duplicate.sum()),
      'unreported_grid_is_not_zero':True,'publication_ready':False})
    return {'rows':len(per),'path':str(dest)}

def run(root,workers=8):
    root=Path(root)
    files=sorted((root/'data/staged/cee_all').rglob('GISD30_1985-2020_*.tif'))
    # All files in staged 12 RAR archives, not a partial 3-source benchmark.
    if len(files)<953:raise ValueError(f'Only {len(files)} GISD30 original rasters staged. Frozen server inventory previously recorded 953; stage all 12 RARs first')
    if len(set(p.name for p in files))!=len(files):
        raise ValueError('Duplicate GISD30 native 5deg file names across RAR archive parts')
    if not 1<=workers<=24:raise ValueError('GISD 30m use <=24 worker processes, memory-heavy C++ extraction')
    out,jid=prepare_directory(root/'data/derived/cee_all_global_v2/gisd30_history',
      {'grid':file_identity(root/'gf10_global_nonantarctic_land.parquet'),
       'native_source_identity':[file_identity(p) for p in files],
       'algorithm':'8_class_cumulative_30m_native_unique_frac_v2'})
    tasks=[(str(p),str(root/'gf10_global_nonantarctic_land.parquet'),str(out),jid) for p in files]
    stats=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        future=[pool.submit(_source_one,t) for t in tasks]
        for i,f in enumerate(as_completed(future),1):
            stats.append(f.result())
            if i%25==0 or i==len(future):print(f'[gisd30] {i}/{len(future)} TIFFs',flush=True)
    inputs=sorted((out/'parts').glob('GISD30_1985-2020_*.parquet'))
    if len(inputs)!=len(files):raise ValueError('GISD30 source-shard coverage incomplete')
    full=out/'gf10_gisd30_history_1985_2020.parquet'
    if full.exists() and (out/'combine_qc.json').exists():
        combined={'rows':len(pd.read_parquet(full,columns=['grid_id'])),'path':str(full),'status':'REUSED'}
    else:combined=_combine(root,inputs,out)
    qc={'status':'ALL_GISD30_SOURCE_TILES_PROCESSED_NEEDS_SPATIAL_SEAM_QA',
        'n_source_tif':len(files),'n_reused':sum(x['status']=='REUSED' for x in stats),
        'n_written':sum(x['status']=='WROTE' for x in stats),
        'n_grid':combined['rows'],'epochs':YEARS,'publication_ready':False}
    write_json(out/'run_qc.json',qc)
    return qc
