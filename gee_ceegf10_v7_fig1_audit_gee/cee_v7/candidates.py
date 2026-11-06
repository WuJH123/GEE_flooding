"""Deterministic same-grid/calendar candidate dates and geographically compact request groups."""
from __future__ import annotations
import datetime as dt,pathlib
import numpy as np
import pandas as pd
from . import core
OFFSETS=(-84,-77,-70,-63,-56,-49,-42,-35,-28,-21,-14,14,21,28,35,42,49,56,63,70,77,84)


def _nearest(days,target,buffer):
    import bisect
    i=bisect.bisect_left(days,target)
    return (i<len(days) and abs(days[i]-target)<=buffer) or (i>0 and abs(days[i-1]-target)<=buffer)


def build_candidates(cases,n=4,exclude=7,end='2023-12-31',start='2021-01-01'):
    if not 1<=n<=12:raise ValueError('Candidate count must be 1..12')
    if not 7<=exclude<=21:raise ValueError('Exclusion buffer must be 7..21 days')
    if cases.case_id.duplicated().any():raise ValueError('Duplicate case IDs')
    if not cases.case_control.eq('reported_case').all():raise ValueError('Only source-derived reported cases permitted')
    records=cases[['case_id','grid_id','city_id','date_utc','pair_id']].copy()
    records['case_control']='reported_case'
    records['reference_case_date']=records.date_utc
    records['offset_days']=0
    records['is_verified_no_flood']=False
    records['utc_anchor_type']='SOURCE_LOCAL_CALENDAR_DAY_AS_UTC_PROXY'
    records['sampling_protocol']='V7_SOURCE_DAY_PROVISIONAL_CASE'
    datearr=lambda s:sorted({dt.date.fromisoformat(x).toordinal() for x in s})
    citydays={str(k):datearr(g.date_utc) for k,g in cases.groupby('city_id',sort=False)}
    grid_days={str(k):datearr(g.date_utc) for k,g in cases.groupby('grid_id',sort=False)}
    pool=[];taken=set();unmatched=0
    for row in cases.sort_values('case_id').itertuples(index=False):
        source=dt.date.fromisoformat(row.date_utc)
        offsets=sorted(OFFSETS,key=lambda x:core.stable_id(row.case_id,x,n=32))
        count=0
        for offset in offsets:
            d=source+dt.timedelta(days=offset)
            ds=d.isoformat();q=d.toordinal()
            if ds<start or ds>end:continue
            if (str(row.grid_id),ds) in taken:continue
            if _nearest(citydays[str(row.city_id)],q,exclude) or _nearest(grid_days[str(row.grid_id)],q,exclude):continue
            taken.add((str(row.grid_id),ds))
            pool.append({'case_id':row.case_id,'grid_id':row.grid_id,'city_id':row.city_id,
                         'date_utc':ds,'pair_id':row.pair_id,'case_control':'unlabeled_calendar_candidate',
                         'reference_case_date':row.date_utc,'offset_days':offset,
                         'is_verified_no_flood':False,'utc_anchor_type':'SOURCE_LOCAL_CALENDAR_DAY_AS_UTC_PROXY',
                         'sampling_protocol':'SAME_GRID_SAME_WEEKDAY_NEAR_SEASON_NEWS_EXCLUSION_7D_V7'})
            count+=1
            if count>=n:break
        if count==0:unmatched+=1
    cand=pd.DataFrame(pool,columns=records.columns)
    if cand.empty:raise ValueError('No candidate comparisons could be generated')
    out=pd.concat([records,cand],ignore_index=True)
    if out.loc[out.case_control=='unlabeled_calendar_candidate'].duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate candidates')
    return out,{'n_reported_cases':len(cases),'n_calendar_unlabeled':len(cand),'n_cases_without_candidates':unmatched,
                'candidate_label':'UNLABELED_NOT_CONFIRMED_DRY','no_flood_negative_count':0,
                'case_days_UTC_proxy_not_local_midnight_converted':True}


def make_plan(candidates,grid,max_cells=40):
    if not 1<=max_cells<=100:raise ValueError('Bounded GEE table group size must be <=100')
    keys=grid[['grid_id','grid_x','grid_y']].copy();keys.grid_id=keys.grid_id.astype(str)
    dates=candidates[['grid_id','date_utc']].copy().drop_duplicates()
    dates.grid_id=dates.grid_id.astype(str)
    if dates.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate request key')
    dates=dates.merge(keys,on='grid_id',how='left',validate='many_to_one')
    if dates.grid_x.isna().any():raise ValueError('Candidate grid not in frozen GF10')
    dates['tile_x0']=np.floor_divide(dates.grid_x.astype('int64'),10)*10
    dates['tile_y0']=np.floor_divide(dates.grid_y.astype('int64'),10)*10
    dates=dates.sort_values(['date_utc','tile_x0','tile_y0','grid_id']).reset_index(drop=True)
    dates['part']=dates.groupby(['date_utc','tile_x0','tile_y0'],sort=False).cumcount().floordiv(max_cells)
    groups=dates.groupby(['date_utc','tile_x0','tile_y0','part'],sort=True)
    plan=groups.agg(n_grid_days=('grid_id','size'),first_grid=('grid_id','first'),
                    last_grid=('grid_id','last')).reset_index()
    plan['request_key']=['V7W_'+d.replace('-','')+'_'+str(x)+'_'+str(y)+'_'+str(k)
                         for d,x,y,k in zip(plan.date_utc,plan.tile_x0,plan.tile_y0,plan.part)]
    dates=dates.merge(plan[['date_utc','tile_x0','tile_y0','part','request_key']],
       on=['date_utc','tile_x0','tile_y0','part'],validate='many_to_one')
    if plan.request_key.duplicated().any() or plan.n_grid_days.max()>max_cells:raise ValueError('Invalid GEE plan')
    plan['source_calendar_UTC_proxy']=True
    plan['collection_source']='IMERG_V07_permanent+ERA5_LAND_DAILY_AGGR_prevday'
    plan['output_aggregation']='native_approx_0.1_degree_area_weighted_GF10_polygons'
    return dates,plan


def write_cohort(cases_path,grid_path,out,n=4,strict_grid=True,max_cells=40):
    import pyarrow
    out=pathlib.Path(out)
    if out.exists() and any(out.iterdir()):raise FileExistsError('New output directory required')
    out.mkdir(parents=True,exist_ok=True)
    cases=pd.read_parquet(cases_path)
    # Cases eligible for GEE date pre-extraction irrespective of manual review status;
    # verified status is retained, never promoted by this function.
    candidates,report=build_candidates(cases,n)
    grid=core.check_grid(grid_path,strict=strict_grid)
    dates,plan=make_plan(candidates,grid,max_cells=max_cells)
    candidates.to_parquet(out/'reported_and_UNLABELED_calendar_candidates.parquet',index=False)
    dates.to_parquet(out/'unique_GF10_UTC_proxy_days.parquet',index=False)
    plan.to_csv(out/'gee_weather_date_tile_plan.csv',index=False)
    qc={'status':'PREEXTRACT_ONLY_CASES_AND_UNLABELED_CANDIDATES',**report,
       'source_cases_sha256':core.digest(cases_path),'frozen_grid_sha256':core.digest(grid_path),
       'planned_grid_dates':len(dates),'planned_GEE_tasks':len(plan),'n_distinct_utc_proxy_dates':int(dates.date_utc.nunique()),
       'no_automatic_global_submission':True,'max_cells_per_task':max_cells}
    core.write_json(out/'cohort_and_weather_plan_qc.json',qc)
    return qc
