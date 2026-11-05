"""Two-stage, documented sampling: real reports -> calendar candidates -> weather match.

Never equate no report with confirmed no flooding. No fabricated event/storm IDs.
All inputs must have verifiable original reporting provenance, day precision and
10km spatial attribution supplied by an audited Figure1 output.
"""
from __future__ import annotations
import hashlib,json,pathlib,datetime as dt
import numpy as np
import pandas as pd
from .common import readtab,source_columns,sha,writetab,save,FINAL_V07_END
REQUIRED=('source_event_id','grid_id','date_utc','city_id','label_source',
          'date_precision','location_precision')
DATE_ALLOWED={'exact_day','verified_day','day'}
LOC_ALLOWED={'grid_exact','street','neighborhood','high_specificity'}
OFFSETS=(-63,-56,-49,-42,-35,-28,-21,-14,14,21,28,35,42,49,56,63)


def inspect(path):
    cols=source_columns(path)
    return {'file':str(path),'columns':cols,'required_semantics':list(REQUIRED),
       'schema_mapping':'Map each required semantic to a REAL column; do not infer date precision or city from news text.',
       'status':'NEEDS_AUDITED_MAPPING'}


def freeze_cases(input_path,mapping,grid_path,out_dir,strict_grid=True,start='2021-01-01',end=FINAL_V07_END):
    from .common import check_grid
    out=pathlib.Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    if set(mapping)!=set(REQUIRED):raise ValueError('Mapping must contain exactly these semantics: '+str(REQUIRED))
    cols=source_columns(input_path)
    missing=[v for v in mapping.values() if v not in cols]
    if missing:raise ValueError('Mapping points to missing source columns: '+str(missing))
    src=readtab(input_path,list(set(mapping.values())))
    data=pd.DataFrame({k:src[v] for k,v in mapping.items()})
    n_raw=len(data)
    # Null/low-precision source rows are EXCLUDED with an explicit count,
    # never assigned an invented grid, city or report date.
    blank=pd.Series(False,index=data.index)
    for k in REQUIRED:
        blank |=data[k].isna()
        data[k]=data[k].astype('string').str.strip()
        blank |=data[k].fillna('').eq('')
    dtv=pd.to_datetime(data.date_utc,utc=True,errors='coerce')
    bad_time=dtv.isna()|dtv.dt.hour.ne(0)|dtv.dt.minute.ne(0)|dtv.dt.second.ne(0)
    data['date_utc']=dtv.dt.strftime('%Y-%m-%d')
    excluded_date=~data.date_utc.between(start,end)
    excluded_precision=~data.date_precision.isin(DATE_ALLOWED)
    excluded_location=~data.location_precision.isin(LOC_ALLOWED)
    grid=check_grid(grid_path,strict=strict_grid)
    ids=set(grid.grid_id.astype(str))
    excluded_grid=~data.grid_id.isin(ids)
    # Invalid/low specificity records remain in QC but cannot be used in main cohort.
    eligible=~(blank|bad_time|excluded_date|excluded_precision|excluded_location|excluded_grid)
    valid=data[eligible].copy()
    valid['case_control']='reported_case'
    valid['sampling_protocol']='FIG1_HIGH_SPECIFICITY_REPORTED_EXACT_UTC_DAY_V6'
    valid['source_event_id']=valid.source_event_id.astype(str)
    # Reporting duplicates for one city/grid/day count as one grid-day case;
    # expose the distinct original IDs and source-family bundle for sensitivity.
    bundle=valid.groupby(['grid_id','date_utc','city_id'],sort=True).agg(
        original_event_ids=('source_event_id',lambda a:'|'.join(sorted(set(a)))),
        observation_families=('label_source',lambda a:'|'.join(sorted(set(a)))),
        n_original_records=('source_event_id','size')).reset_index()
    bundle['case_id']=[hashlib.sha256((r.grid_id+'|'+r.date_utc+'|'+r.city_id).encode()).hexdigest()[:24]
                       for r in bundle.itertuples(index=False)]
    bundle['case_control']='reported_case'
    bundle['storm_id']=pd.NA
    bundle['storm_status']='NOT_OBSERVED_OR_UNVERIFIED'
    bundle['sampling_protocol']='FIG1_HIGH_SPECIFICITY_EXACT_GRID_DAY_V6'
    path=out/'reported_grid_day_cases.parquet';writetab(bundle,path)
    report={'status':'REPORTED_CASES_ONLY_NOT_FLOOD_TRUTH','input':str(input_path),
            'input_sha256':sha(input_path),'gf10_sha256':sha(grid_path),'mapping':mapping,
            'n_source_records':n_raw,'n_eligible_records':int(eligible.sum()),
            'n_reported_grid_day_cases':len(bundle),
            'excluded_null_or_blank':int(blank.sum()),'excluded_non_UTC_calendar_day':int(bad_time.sum()),
            'excluded_date':int(excluded_date.sum()),'excluded_time_precision':int(excluded_precision.sum()),
            'excluded_location_precision':int(excluded_location.sum()),'excluded_not_GF10':int(excluded_grid.sum()),
            'duplicate_records_collapsed':int(eligible.sum())-len(bundle),
            'label_semantics':'reported flood observation, not independently confirmed inundation',
            'allowed_date_end':FINAL_V07_END,
            'source_provenance_required':'must verify Figure1 label_source and precision columns upstream'}
    save(out/'reported_cases_qc.json',report)
    return bundle,report


def generate_calendar_candidates(cases,n_candidates=8,exclusion_days=7):
    if not 1<=n_candidates<=12:raise ValueError('n_candidates must be 1..12')
    if not 7<=exclusion_days<=14:raise ValueError('exclusion days 7..14')
    frame=cases.copy()
    if frame.case_id.duplicated().any():raise ValueError('Duplicate case ID')
    if not set(frame.case_control)=={'reported_case'}:raise ValueError('Case-only input required')
    # Arrays of integer UTC days and binary search: O(cases * offsets * log N),
    # not O(cases * city-report-length), which would be untenable globally.
    to_days=lambda series:np.sort(pd.to_datetime(series).to_numpy(dtype='datetime64[D]').astype('int64'))
    by_city={str(city):to_days(z.date_utc) for city,z in frame.groupby('city_id',sort=False)}
    by_grid={str(grid):to_days(z.date_utc) for grid,z in frame.groupby('grid_id',sort=False)}
    def near(days,target,tolerance):
        pos=int(np.searchsorted(days,target))
        return (pos<len(days) and abs(int(days[pos])-target)<=tolerance) or \
               (pos>0 and abs(int(days[pos-1])-target)<=tolerance)
    taken=set();rows=[];unmatched=[]
    for r in frame.sort_values('case_id').itertuples(index=False):
        day=pd.Timestamp(r.date_utc)
        offsets=sorted(OFFSETS,key=lambda x:hashlib.sha256((str(r.case_id)+'|'+str(x)).encode()).hexdigest())
        found=0
        for offset in offsets:
            candidate=day+dt.timedelta(days=int(offset))
            ds=candidate.strftime('%Y-%m-%d')
            if not ('2021-01-01'<=ds<=FINAL_V07_END):continue
            # Conservative label-derived exclusion only; it does not prove an unreported day was dry.
            index_day=int(np.datetime64(ds,'D').astype('int64'))
            if near(by_city[str(r.city_id)],index_day,exclusion_days) or \
               near(by_grid[str(r.grid_id)],index_day,exclusion_days):continue
            pairid='pair_'+r.case_id
            ident=(str(r.grid_id),ds)
            if ident in taken:continue
            taken.add(ident)
            rows.append({'pair_id':pairid,'case_id':r.case_id,'grid_id':r.grid_id,
                         'city_id':r.city_id,'date_utc':ds,'case_control':'unlabeled_calendar_candidate',
                         'reference_case_date':r.date_utc,'offset_days':offset,
                         'storm_id':None,'storm_status':'PENDING_INDEPENDENT_STORM_CATALOG',
                         'sampling_protocol':'SAME_GRID_SAME_WEEKDAY_PLUS_MINUS_14_TO_63_DAYS_EXCL_CITY_REPORT_7D_V6'})
            found+=1
            if found>=n_candidates:break
        if found==0:unmatched.append(str(r.case_id))
    controls=pd.DataFrame(rows)
    if controls.empty:raise ValueError('No eligible comparison dates; no synthetic negatives created')
    a=frame[['case_id','grid_id','date_utc','city_id']].copy()
    a['pair_id']='pair_'+a.case_id
    a['case_control']='reported_case'
    a['reference_case_date']=a.date_utc
    a['offset_days']=0
    a['storm_id']=None
    a['storm_status']='PENDING_INDEPENDENT_STORM_CATALOG'
    a['sampling_protocol']='FIG1_HIGH_SPECIFICITY_EXACT_GRID_DAY_V6'
    allrows=pd.concat([a[controls.columns],controls],ignore_index=True)
    report={'status':'PRE_WEATHER_UNLABELED_CANDIDATE_COHORT','n_reported_cases':len(a),
            'n_unlabeled_calendar_candidates':len(controls),'n_pairs_without_candidate':len(unmatched),
            'no_candidate_case_ids':unmatched[:30],
            'storm_catalog_verified':False,
            'not_true_flood_negatives':True,'weather_matched':False,
            'duplicate_candidate_grid_date':int(controls.duplicated(['grid_id','date_utc']).sum())}
    return allrows,report


def make_request_plan(candidates,grid):
    g=grid[['grid_id','grid_x','grid_y']].copy();g.grid_id=g.grid_id.astype(str)
    d=candidates[['grid_id','date_utc']].copy().drop_duplicates()
    d.grid_id=d.grid_id.astype(str)
    d=d.merge(g,on='grid_id',validate='many_to_one')
    if len(d)!=len(candidates[['grid_id','date_utc']].drop_duplicates()):raise ValueError('Candidate grid ID absent from GF10')
    d['tile_x0']=d.grid_x.floordiv(10)*10
    d['tile_y0']=d.grid_y.floordiv(10)*10
    plan=d.groupby(['date_utc','tile_x0','tile_y0'],sort=True).agg(
          n_grid_days=('grid_id','size')).reset_index()
    plan['request_key']=['M0_'+dt.replace('-','')+'_'+str(x)+'_'+str(y) for dt,x,y in
                         zip(plan.date_utc,plan.tile_x0,plan.tile_y0)]
    if plan.request_key.duplicated().any() or plan.n_grid_days.max()>100:raise ValueError('Invalid date-tile group')
    return d,plan
