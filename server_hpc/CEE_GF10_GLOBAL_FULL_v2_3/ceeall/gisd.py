"""GISD30 native 30m classes -> GF10 impervious 2000/2020 summaries.

No resampling of raw category integers. Every staged tile is processed separately;
missing source coverage stays missing. Counts approximate equal-area only within a
small GF10 polygon because global source pixels are geographic degrees. Per-source
counts are combined with matching valid-source weights, and are NOT coast-clipped.
"""
from __future__ import annotations
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import re
import numpy as np
from .common import atomic_json,atomic_parquet,fidentity,ensure_job,verify_frozen_grid
from .common import gf10_bounds

def _gf10_source_overlap_mask(x,y,bounds,padding_m=0):
    """Conservative AABB spatial candidate test; limits are MIN then MAX.

    The prior version mistakenly named the right boundary xmin and the left
    boundary xmax.  This pure helper is tested independently before any 953
    native GISD30 TIFFs are read.
    """
    import numpy as np
    x=np.asarray(x,dtype=np.int64);y=np.asarray(y,dtype=np.int64)
    left=x*10000;right=(x+1)*10000
    bottom=y*10000;top=(y+1)*10000
    west,south,east,north=map(float,bounds)
    return (left<=east+padding_m)&(right>=west-padding_m)&\
           (bottom<=north+padding_m)&(top>=south-padding_m)

def _source_one(job):
    source,gridfile,out,jobid=job
    import rasterio,geopandas as gpd,pandas as pd
    from rasterio.warp import transform_bounds
    from shapely.geometry import box
    from exactextract import exact_extract
    source=Path(source);out=Path(out);dest=out/(source.stem+'.parquet')
    qc=out/(source.stem+'.qc.json')
    if dest.exists() and qc.exists():
        d=__import__('json').loads(qc.read_text('utf8'))
        if (d.get('job_id')==jobid and d.get('status')=='OK' and
            d.get('source_identity')==fidentity(source)):
            import pyarrow.parquet as pq
            if pq.ParquetFile(dest).metadata.num_rows!=d['rows']:
                raise ValueError('GISD30 cached Parquet row count differs '+str(dest))
            return {'status':'REUSED','file':source.name,'n':d['rows']}
        raise ValueError('GISD30 output QC mismatch '+str(dest))
    if dest.exists()!=qc.exists():raise FileExistsError('Unpaired GISD30 shard '+str(dest))
    with rasterio.open(source) as src:
        if not src.crs or src.count!=1 or not src.crs.is_geographic:raise ValueError('GISD30 must have original geographic CRS')
        bb=transform_bounds(src.crs,'EPSG:6933',*src.bounds,densify_pts=61)
        g=pd.read_parquet(gridfile,columns=['grid_id','grid_x','grid_y'])
        m=_gf10_source_overlap_mask(g.grid_x.to_numpy(),g.grid_y.to_numpy(),bb)
        g=g.loc[m].copy()
        if g.empty:
            atomic_parquet(pd.DataFrame({'grid_id':pd.Series([],dtype=str),
               'valid_native_count':pd.Series([],dtype=float),
               'impervious_2000_count':pd.Series([],dtype=float),
               'impervious_2020_count':pd.Series([],dtype=float)}),dest)
            atomic_json(qc,{'status':'OK','job_id':jobid,'rows':0,'valid_rows':0,'source_identity':fidentity(source)})
            return {'status':'WROTE','file':source.name,'n':0}
        poly=[box(*gf10_bounds(x,y)) for x,y in zip(g.grid_x,g.grid_y)]
        zones=gpd.GeoDataFrame({'grid_id':g.grid_id.to_numpy()},geometry=poly,crs='EPSG:6933').to_crs(src.crs)
        invalid=(zones.bounds.maxx-zones.bounds.minx)>5
        if invalid.any():zones.loc[invalid,'geometry']=None
        good=zones.geometry.notna() & ~zones.geometry.is_empty
        if not good.any():
            raw=pd.DataFrame(columns=['grid_id','count','unique','frac'])
        else:
            raw=exact_extract(str(source),zones.loc[good],['count','unique','frac'],include_cols=['grid_id'],output='pandas')
        if len(raw)!=int(good.sum()):raise ValueError('Unexpected ExactExtract nonempty geometry output length')
        cnt=pd.to_numeric(raw['count'],errors='coerce').to_numpy(dtype=float)
        n2000=np.full(len(raw),np.nan);n2020=np.full(len(raw),np.nan)
        for i,(codes,shares) in enumerate(zip(raw['unique'],raw['frac'])):
            if not np.isfinite(cnt[i]) or cnt[i]<=0:continue
            if codes is None or shares is None:raise ValueError('Inconsistent categorical GISD pixel counts')
            codes=np.asarray(codes,dtype=int);shares=np.asarray(shares,dtype=float)
            if len(codes)!=len(shares) or not np.all(np.isfinite(shares)):
                raise ValueError('GISD invalid class/frac pairing')
            if (shares< -1e-8).any() or shares.sum()>1.001 or ((codes<0)|(codes>8)).any():
                raise ValueError('GISD source has unknown class code or fraction')
            n2000[i]=cnt[i]*shares[(codes>=1)&(codes<=4)].sum()
            n2020[i]=cnt[i]*shares[(codes>=1)&(codes<=8)].sum()
        vals=pd.DataFrame({'grid_id':raw.grid_id,'valid_native_count':cnt,
             'impervious_2000_count':n2000,'impervious_2020_count':n2020})
        if vals.grid_id.duplicated().any():raise ValueError('duplicate GF10 mapping in source')
        vals=vals.loc[vals.valid_native_count>0].copy()
        atomic_parquet(vals,dest)
        atomic_json(qc,{'status':'OK','rows':len(vals),'job_id':jobid,'source':str(source),
            'native_class_recoding':{'2000':[1,2,3,4],'2020':[1,2,3,4,5,6,7,8]},
            'source_identity':fidentity(source),
            'not_land_polygon_clipped':True,'publication_ready':False})
        return {'status':'WROTE','file':source.name,'n':len(vals)}

def run(root,workers=8,max_sources=3):
    root=Path(root)
    paths=sorted((root/'data/staged/cee_all').rglob('GISD30_1985-2020_*.tif'))
    if not paths:raise FileNotFoundError('No staged GISD30 TIFFs (run stage gisd first)')
    if max_sources is not None:paths=paths[:max_sources]
    if not 1<=workers<=32:raise ValueError('Workers 1..32')
    out=root/'data/derived/cee_all_v11/gisd30_parts_v12'
    # Stable parent job identity: staging 1 RAR for a pilot and later staging
    # all 12 RARs must not invalidate already-verified source partitions.
    # Every source shard separately fingerprints its TIFF stat+mtime.
    jid=ensure_job(out,{
        'grid_source':fidentity(root/'gf10_global_nonantarctic_land.parquet'),
        'method':'native_30m_classes_exactextract_count_frac_v12',
        'source_family':'GISD30_1985-2020', 'expected_global_sources':953})
    args=[(str(p),str(root/'gf10_global_nonantarctic_land.parquet'),str(out),jid) for p in paths]
    if workers==1:responses=[_source_one(x) for x in args]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(_source_one,x) for x in args]
            responses=[f.result() for f in as_completed(futures)]
    qc={'status':'PILOT_PARTIAL' if max_sources else 'PARTS_COMPLETE_NEEDS_MOSAIC_QA',
        'expected_total_source_tif':len(list((root/'data/staged/cee_all').rglob('GISD30_1985-2020_*.tif'))),
        'n_source_processed':len(responses),'n_reused':sum(x['status']=='REUSED' for x in responses),
        'n_written':sum(x['status']=='WROTE' for x in responses),'source_5deg_overlap_not_deduplicated':True,
        'not_land_polygon_clipped':True,'publication_ready':False}
    atomic_json(out/'run_qc.json',qc)
    return qc

def combine(root,require_953=True):
    import pandas as pd
    root=Path(root);src=root/'data/derived/cee_all_v11/gisd30_parts_v12'
    files=sorted(src.glob('GISD30_*.parquet'))
    if not files:raise FileNotFoundError('GISD30 source parts missing')
    if require_953 and len(files)!=953:raise ValueError(f'Only {len(files)} source partitions; expected 953')
    jid=__import__('json').loads((src/'job.json').read_text(encoding='utf8'))['job_id']
    for fp in files:
        q=fp.with_suffix('.qc.json')
        if not q.exists():raise ValueError('Missing GISD30 tile QC '+str(fp))
        d=__import__('json').loads(q.read_text(encoding='utf8'))
        if d.get('job_id')!=jid or d.get('status')!='OK':
            raise ValueError('Invalid GISD30 cached tile QC '+str(q))
        import pyarrow.parquet as pq
        if pq.ParquetFile(fp).metadata.num_rows!=d.get('rows'):
            raise ValueError('GISD30 partition QC row count mismatch '+str(fp))
    # 953 source shards may overlap a GF10 cell near archive seams;
    # source-valid pixel counts are summed and potential source overlap is flagged.
    parts=[pd.read_parquet(p) for p in files]
    df=pd.concat(parts,ignore_index=True)
    if df.empty:raise ValueError('No valid GISD30 pixels')
    df=df.groupby('grid_id',as_index=False).agg(
        valid_native_count=('valid_native_count','sum'),
        impervious_2000_count=('impervious_2000_count','sum'),
        impervious_2020_count=('impervious_2020_count','sum'),
        n_source_tiles=('grid_id','size'))
    for year in (2000,2020):
        df[f'gisd30_impervious_{year}_valid_data_fraction']=df[f'impervious_{year}_count']/df.valid_native_count
        bad=df[f'gisd30_impervious_{year}_valid_data_fraction'].gt(1.0001)
        if bad.any():raise ValueError('Impervious fraction >1 '+str(int(bad.sum())))
    df['gis30_possible_duplicate_source_overlap']=df.n_source_tiles>1
    dest=root/'data/derived/cee_all_v11'/('gisd30' if require_953 else 'gisd30_pilot')
    j=ensure_job(dest,{'parent_source_job':__import__('json').loads((src/'job.json').read_text('utf8'))['job_id'],
                       'method':'count_weighted_native_30m_v12','require_953':require_953})
    out=dest/'gf10_gisd30_2000_2020.parquet'
    if out.exists():raise FileExistsError('Refusing to overwrite GISD results '+str(out))
    atomic_parquet(df,out)
    atomic_json(dest/'qc.json',{'status':'OUTPUT_NEEDS_TILE_COVERAGE_AND_COAST_QA',
       'n_source_files':len(files),'n_grid_with_source':len(df),'n_source_overlap_geometries':int(df.gis30_possible_duplicate_source_overlap.sum()),
       'not_land_polygon_clipped':True,'publication_ready':False})
    return {'rows':len(df),'file':str(out)}
