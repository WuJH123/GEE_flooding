"""Strictly join finished static products to frozen GF10 IDs, never fill NA with zero."""
from pathlib import Path
import pandas as pd
from .common import verify_frozen_grid,atomic_parquet,atomic_json,ensure_job,read_json,fidentity

GHSL=('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020')

def collect(root,include_optional=False,require_ghsl=True,allow_pilot=False):
    root=Path(root)
    grid,meta=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',strict=True)
    full_ids=grid[['grid_id','grid_x','grid_y','land_area_km2']].copy()
    out=full_ids
    used=[];missing=[]
    candidates=[]
    for p in GHSL:
        folder=root/'data/derived'/f'hpc_exact_{p}_v2'
        if not folder.is_dir():missing.append(p);continue
        qcfile=folder/'run_qc.json'
        if not qcfile.exists():missing.append(p+'_NO_QC');continue
        qc=read_json(qcfile)
        if not allow_pilot and qc.get('status')!='ALL_TILES_NATIVE_EXACT_NEEDS_COAST_QA':
            raise ValueError(f'GHSL {p} incomplete status={qc.get("status")}; never label as global')
        files=sorted((folder/'tiles').glob('tile_*.parquet'))
        if len(files)!=715 and not allow_pilot:raise ValueError(f'GHSL {p} has only {len(files)}/715 shards')
        if not allow_pilot and qc.get('n_tasks')!=715:
            raise ValueError(f'GHSL {p} task count mismatch {qc.get("n_tasks")}')
        candidates.append(('ghsl_'+p,files))
    if require_ghsl and len(candidates)<5:raise ValueError('Five complete GHSL native sources required: missing '+str(missing))
    if include_optional:
        base=root/'data/derived/cee_all_v11'
        for profile in ('gmted','worldclim-bio','worldclim-monthly','grip-density'):
            folder=base/profile
            if not folder.exists():continue
            for source in sorted(folder.iterdir()):
                if not source.is_dir() or not (source/'run_qc.json').exists():continue
                qc=read_json(source/'run_qc.json')
                if qc.get('status')!='FULL_TILES_NATIVE_EXACT_NEEDS_LAND_QA':
                    missing.append(str(source)+'_NOT_FULL');continue
                files=sorted((source/'tiles').glob('tile_*.parquet'))
                if len(files)!=715:missing.append(str(source)+'_MISSING_SHARDS');continue
                candidates.append((profile+'_'+source.name,files))
        gisd=base/'gisd30/gf10_gisd30_2000_2020.parquet'
        if gisd.exists():candidates.append(('gisd30',[gisd]))
        vector=base/'vector'
        if vector.is_dir():
            for p in sorted(vector.glob('*/link.parquet')):
                candidates.append(('vector_'+p.parent.name,[p]))
    for name,paths in candidates:
        frames=[pd.read_parquet(x) for x in paths]
        frame=pd.concat(frames,ignore_index=True)
        if frame.grid_id.duplicated().any():raise ValueError('Duplicate grid IDs in '+name)
        unknown=~frame.grid_id.isin(full_ids.grid_id)
        if unknown.any():raise ValueError(f'{name} contains unknown grid IDs: {int(unknown.sum())}')
        cols=[c for c in frame.columns if c!='grid_id']
        repeats=set(cols)&set(out.columns)
        if repeats:
            # Product QC flags can be duplicated between GHSL bands; keep distinct provenance.
            frame=frame.rename(columns={c:name+'__'+c for c in repeats})
        out=out.merge(frame,on='grid_id',how='left',validate='one_to_one',sort=False)
        if len(out)!=len(full_ids):raise ValueError('Output row conservation failed after '+name)
        used.append({'source':name,'rows':len(frame),'columns':len(frame.columns)})
        del frames,frame
    dest=root/'data/derived/cee_all_v11/assembled'
    job=ensure_job(dest,{'grid':fidentity(root/'gf10_global_nonantarctic_land.parquet'),
         'inputs':used,'optional':include_optional,'allow_pilot':allow_pilot,'method':'left_join_preserve_NA_v11'})
    target=dest/'gf10_global_static_wide.parquet'
    if target.exists():raise FileExistsError('Refusing to overwrite existing wide table '+str(target))
    atomic_parquet(out,target)
    atomic_json(dest/'qc.json',{'status':'MERGED_NEEDS_SOURCE_NUMERIC_AND_LAND_QA','rows':len(out),
        'unique_ids':int(out.grid_id.nunique()),'n_columns':len(out.columns),'used':used,'missing':missing,
        'not_land_polygon_clipped':True,'not_all_observed_as_physical_flood':True,
        'publication_ready':False,'job_id':job})
    return {'rows':len(out),'columns':len(out.columns),'used':used,'output':str(target),'missing':missing}

def merge_year(root,year):
    root=Path(root)
    sources=sorted((root/'data/derived/cee_all_v11/era5ex').glob(f'*/year_{year}.parquet'))
    if not sources:raise FileNotFoundError(f'No ERA5EX annual results for year={year}')
    grid,_=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',True)
    df=grid[['grid_id']].assign(year=int(year))
    for path in sources:
        a=pd.read_parquet(path)
        if len(a)!=len(grid) or a.grid_id.duplicated().any() or not (a.year==year).all():
            raise ValueError('Incomplete ERA5EX annual source '+str(path))
        cols=set(df.columns)&set(a.columns)-{'grid_id','year'}
        if cols:raise ValueError('Duplicate ERA5EX indicator names: '+str(cols))
        df=df.merge(a,on=['grid_id','year'],how='left',validate='one_to_one')
    dest=root/'data/derived/cee_all_v11/era_annual_merged'
    j=ensure_job(dest,{'year':year,'sources':[str(p) for p in sources],
         'method':'annual_native_source_nearest_v11'})
    out=dest/f'gf10_era5ex_{year}.parquet'
    if out.exists():raise FileExistsError('Annual output exists '+str(out))
    atomic_parquet(df,out)
    atomic_json(dest/f'gf10_era5ex_{year}_qc.json',{'status':'MERGED_ERA_ANNUAL_PROXY_NOT_EVENT_DAY','n_cells':len(df),
       'n_variables':len(df.columns)-2,'publication_ready':False,'job_id':j})
    return {'columns':len(df.columns),'rows':len(df),'file':str(out)}
