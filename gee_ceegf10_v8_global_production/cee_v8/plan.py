"""Idempotent macro-batching of verified v7 GF10 x UTC-proxy date requests.

All date rows retained; macro batches share up to 4 different dates in one EE
FeatureCollection export. No positional or geographic inference of observed floods.
"""
from __future__ import annotations
import datetime as dt,pathlib
import pandas as pd
from . import core


def calendar_dates(v7_path,add_case_day_uncertainty=False):
 v7=pathlib.Path(v7_path)
 pf=v7/'plans'/'unique_GF10_UTC_proxy_days.parquet'
 qc=core.read_json(v7/'plans'/'cohort_and_weather_plan_qc.json')
 if not pf.exists() or qc is None or qc.get('status')!='PREEXTRACT_ONLY_CASES_AND_UNLABELED_CANDIDATES':
  raise ValueError('V7 formally audited date plan missing')
 if qc.get('frozen_grid_sha256')!=core.GRID_SHA:raise ValueError('V7 date plan references different GF10')
 if qc.get('planned_grid_dates')!=core.EXPECTED_CASE_DAYS:raise ValueError('V7 date request count differs from independently accepted 196496')
 f=pd.read_parquet(pf,columns=['grid_id','date_utc','grid_x','grid_y'])
 f.grid_id=f.grid_id.astype(str);f.date_utc=f.date_utc.astype(str)
 if len(f)!=core.EXPECTED_CASE_DAYS or f.duplicated(['grid_id','date_utc']).any():raise ValueError('V7 date rows not unique/exhaustive')
 if not f.date_utc.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():raise ValueError('Unverified date format')
 if f.date_utc.gt(core.PERMANENT_END).any() or f.date_utc.lt('2000-01-31').any():raise ValueError('IMERG V07 permanent window violation')
 f['analysis_role']='SOURCE_REPORTED_OR_UNLABELED_CALENDAR_PREEXTRACTION'
 if add_case_day_uncertainty:
  cp=v7/'data'/'case_source'/'reported_source_day_cases_PROVISIONAL.parquet'
  if not cp.is_file():raise FileNotFoundError(cp)
  cases=pd.read_parquet(cp,columns=['grid_id','date_utc']).drop_duplicates()
  a=[]
  for offset in (-1,1):
   tmp=cases.copy();tmp['date_utc']=(pd.to_datetime(tmp.date_utc)+pd.Timedelta(days=offset)).dt.strftime('%Y-%m-%d')
   tmp['analysis_role']=f'CASE_DATE_SENSITIVITY_{offset:+d}D'
   a.append(tmp)
  x=pd.concat(a,ignore_index=True).drop_duplicates(['grid_id','date_utc'])
  missing=x.merge(f[['grid_id','date_utc']],on=['grid_id','date_utc'],how='left',indicator=True)
  missing=missing[missing._merge.eq('left_only')][['grid_id','date_utc','analysis_role']]
  coords=f[['grid_id','grid_x','grid_y']].drop_duplicates('grid_id')
  missing=missing.merge(coords,on='grid_id',how='left',validate='many_to_one')
  if missing[['grid_x','grid_y']].isna().any().any():raise ValueError('Sensitivity grid not in frozen cohort')
  f=pd.concat([f,missing[f.columns]],ignore_index=True)
 return f,{'base_grid_days':core.EXPECTED_CASE_DAYS,'with_source_date_sensitivity':bool(add_case_day_uncertainty),'unique_grid_days':len(f),'source_v7_date_file_sha256':core.sha(pf)}


def batch_rows(f,max_rows=260,max_days=4,geo_span_cells=0):
 """Global-sparse default avoids >100k date+tile tasks, with spatial fallback.

 0 geo span means any location may co-occur, but each actual reduction remains
 polygon-local in native source ~11 km CRS; no global fine resolution reproject.
 Individual failing batches must be split conservatively by geography/time.
 """
 if not (1<=max_rows<=600 and 1<=max_days<=8):raise ValueError('Macro group too large for bounded EE graph')
 if f.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate grid-days')
 f=f.sort_values(['date_utc','grid_x','grid_y','grid_id']).reset_index(drop=True).copy()
 f['week_bucket']=(pd.to_datetime(f.date_utc)-pd.Timestamp('2000-01-03')).dt.days//max_days
 # The bucket is a fixed 4-day window, never assume weekdays or storms.
 if geo_span_cells>0:
  f['bx']=f.grid_x.astype(int).floordiv(geo_span_cells)
  f['by']=f.grid_y.astype(int).floordiv(geo_span_cells)
 else:f['bx']=0;f['by']=0
 batches=[]
 for (_,_,_),grp in f.groupby(['week_bucket','bx','by'],sort=True):
  # Split by rows and by number of distinct dates without splitting date pixels needlessly.
  for i in range(0,len(grp),max_rows):
   sub=grp.iloc[i:i+max_rows]
   keys=sorted(sub.grid_id.astype(str)+'@'+sub.date_utc.astype(str))
   ident='W8_'+core.hashkey(*keys)
   batches.append((sub.index.to_numpy(),ident))
 for loc,key in batches:f.loc[loc,'batch_id']=key
 if f.batch_id.isna().any():raise ValueError('Unassigned weather request')
 q=f.groupby('batch_id').agg(n_rows=('grid_id','size'),days=('date_utc','nunique'),date_min=('date_utc','min'),date_max=('date_utc','max'),x_min=('grid_x','min'),x_max=('grid_x','max'),y_min=('grid_y','min'),y_max=('grid_y','max')).reset_index()
 if q.n_rows.max()>max_rows or q.days.max()>max_days or q.batch_id.duplicated().any():raise ValueError('Macro-batch bounds violated')
 return f,q


def build(root,output,add_case_day_uncertainty=False,max_rows=260,max_days=4,geo_span_cells=0):
 files=core.root_files(root);g=core.validate_grid(files['grid']);core.validate_science(files)
 v7=files['v7']
 f,meta=calendar_dates(v7,add_case_day_uncertainty)
 identity=g[['grid_id','grid_x','grid_y']].copy();identity.grid_id=identity.grid_id.astype(str)
 check=f[['grid_id','grid_x','grid_y']].drop_duplicates().merge(identity,on='grid_id',how='left',validate='one_to_one',suffixes=('','_gf10'))
 if check.grid_x_gf10.isna().any() or not (check.grid_x.eq(check.grid_x_gf10)&check.grid_y.eq(check.grid_y_gf10)).all():raise ValueError('V7 grid coordinates do not match frozen GF10')
 d,summary=batch_rows(f,max_rows,max_days,geo_span_cells)
 p=pathlib.Path(output);p.mkdir(parents=True,exist_ok=True)
 for fp in [p/'weather_grid_days.parquet',p/'weather_batches.csv',p/'frozen_plan_qc.json']:
  if fp.exists():raise FileExistsError('V8 immutable plan already exists: '+str(fp))
 d.to_parquet(p/'weather_grid_days.parquet',index=False)
 summary.to_csv(p/'weather_batches.csv',index=False)
 qc={'status':'FROZEN_GLOBAL_REQUEST_PLAN_NOT_EXPORTED','project':core.PROJECT,'gf10_sha256':core.GRID_SHA,'gf10_rows':core.GRID_ROWS,
 'planned_weather_batches':len(summary),'max_rows':max_rows,'max_dates':max_days,'geo_span_cells':geo_span_cells,
 'weather_rows_file_sha256':core.sha(p/'weather_grid_days.parquet'),'summary_sha256':core.sha(p/'weather_batches.csv'),
 'v7_source_includes_unlabeled_not_dry':True,'source_dates_are_UTC_calendar_proxy_not_verified':True,**meta}
 core.write_json(p/'frozen_plan_qc.json',qc)
 return qc


def split_weather_frame(f):
 """Adaptive deterministic bisection on failure; never abandon original rows."""
 if len(f)<2:raise ValueError('Single grid-day cannot be split; quarantine and investigate')
 s=f.sort_values(['grid_x','grid_y','date_utc','grid_id']).reset_index(drop=True)
 if s.date_utc.nunique()>1:
  a,b=sorted(s.date_utc.unique())[:s.date_utc.nunique()//2],None
  left=s[s.date_utc.isin(a)];right=s[~s.date_utc.isin(a)]
 else:left=s.iloc[:len(s)//2];right=s.iloc[len(s)//2:]
 if len(left)==0 or len(right)==0:raise ValueError('Zero adaptive child')
 if set(left.grid_id+'@'+left.date_utc)&set(right.grid_id+'@'+right.date_utc):raise ValueError('Split overlap')
 return left.copy(),right.copy()


def accepted_v7_weather_rows(v7):
 """Use only actual downloaded source CSVs with validated v7 SHA."""
 from . import core
 ledger=core.read_json(pathlib.Path(v7)/'reports'/'v7_weather_tasks.json',[])
 frames=[]
 for z in ledger:
  if z.get('kind')!='WEATHER_PREEXTRACTION' or z.get('local_qc_pass') is not True:continue
  p=pathlib.Path(z.get('local_file',''))
  if not p.is_file() or core.sha(p)!=z.get('source_csv_sha256'):
   raise ValueError('Previously accepted v7 GEE weather file missing or hash changed: '+str(p))
  a=pd.read_csv(p,dtype={'grid_id':'string','date_utc':'string'})
  if not set(core.FIELDS)<=set(a):raise ValueError('V7 weather source fields missing')
  frames.append(a[core.FIELDS].copy())
 if not frames:return pd.DataFrame(columns=core.FIELDS)
 f=pd.concat(frames,ignore_index=True)
 if f.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate v7 accepted weather keys')
 return f


def build_reuse_plan(root,output,add_case_day_uncertainty=True,max_rows=260,max_days=4,geo_span_cells=0):
 """Plan all 196496 base rows, but do not re-export 46 already accepted ones."""
 files=core.root_files(root);grid=core.validate_grid(files['grid']);core.validate_science(files)
 f,meta=calendar_dates(files['v7'],add_case_day_uncertainty)
 old=accepted_v7_weather_rows(files['v7'])
 if not len(old):raise ValueError('Production needs v7 accepted weather files for source numerical equivalence canary')
 old_keys=set(old.grid_id+'@'+old.date_utc)
 check=f[['grid_id','grid_x','grid_y']].drop_duplicates()
 ref=grid[['grid_id','grid_x','grid_y']].copy();ref.grid_id=ref.grid_id.astype(str)
 a=check.merge(ref,on='grid_id',how='left',suffixes=('','_frozen'),validate='one_to_one')
 if a.grid_x_frozen.isna().any() or not (a.grid_x==a.grid_x_frozen).all() or not (a.grid_y==a.grid_y_frozen).all():
  raise ValueError('Original frozen GF10 coordinates modified')
 keep=(f.grid_id+'@'+f.date_utc).isin(old_keys)
 if int(keep.sum())!=len(old):raise ValueError('V7 46 accepted source rows not contained in immutable cohort')
 needed=f[~keep].copy();d,s=batch_rows(needed,max_rows,max_days,geo_span_cells)
 p=pathlib.Path(output);p.mkdir(parents=True,exist_ok=True)
 for filename in ('weather_grid_days.parquet','weather_batches.csv','accepted_v7_weather.parquet','canary_rows.parquet','frozen_plan_qc.json','merit_batches.csv','merit_quarantine.csv'):
  if (p/filename).exists():raise FileExistsError('Immutable plan already exists '+filename)
 d.to_parquet(p/'weather_grid_days.parquet',index=False)
 s.to_csv(p/'weather_batches.csv',index=False)
 old.to_parquet(p/'accepted_v7_weather.parquet',index=False)
 # Source-identical canary: 3 dates, all 46 observed values, new macro EE graph.
 canary=old[['grid_id','date_utc']].merge(f[['grid_id','date_utc','grid_x','grid_y']],on=['grid_id','date_utc'],validate='one_to_one')
 canary['batch_id']='W8_CANARY_'+core.hashkey(*sorted(canary.grid_id+'@'+canary.date_utc))
 canary.to_parquet(p/'canary_rows.parquet',index=False)
 merit,quarantine=merit_plan(root)
 merit.to_csv(p/'merit_batches.csv',index=False)
 quarantine.to_csv(p/'merit_quarantine.csv',index=False)
 qc={'status':'FROZEN_V8_GLOBAL_PRODUCTION_PLAN_READY_NOT_CLOUD_COMPLETE','gf10_rows':core.GRID_ROWS,
  'gf10_sha256':core.GRID_SHA,'base_date_rows':core.EXPECTED_CASE_DAYS,
  'existing_v7_weather_reused':len(old),'new_weather_rows':len(d),'new_weather_batches':len(s),
  'weather_macro_canary_rows':len(canary),'weather_macro_canary_dates':canary.date_utc.nunique(),
  'merit_safe_tiles_to_run':len(merit),'merit_seam_quarantined_tiles':len(quarantine),
  'no_true_negative_flood_labels':True,'source_date_utc_proxy':True,
  'source_dates_sensitivity_included':add_case_day_uncertainty,
  'weather_plan_sha256':core.sha(p/'weather_grid_days.parquet'),
  'merit_plan_sha256':core.sha(p/'merit_batches.csv'),
  'v7_accepted_weather_sha256':core.sha(p/'accepted_v7_weather.parquet'),
  'v7_accepted_merit_parquet_sha256':core.sha(files['v7']/'data'/'merit_v7_batch5_accepted_partial.parquet'),
  'max_rows_per_weather_batch':max_rows,'max_utc_days_per_batch':max_days,
  'geo_bin_cells':geo_span_cells,**meta}
 core.write_json(p/'frozen_plan_qc.json',qc)
 return qc


def merit_plan(root):
 f=core.root_files(root);core.validate_science(f)
 p=f['v4']/'plans'/'merit_safe_v4.csv'
 if not p.is_file():raise FileNotFoundError(p)
 plan=pd.read_csv(p)
 required={'tile_key','crop_x0','crop_y0','width','height','n_land_cells'}
 if not required<=set(plan):raise ValueError('Frozen v4 safe MERIT schema changed: '+str(required-set(plan)))
 if len(plan)!=16860 or plan.tile_key.duplicated().any():raise ValueError('Frozen 16860 MERIT safe tiles changed')
 done=set()
 for z in core.read_json(f['v6']/'reports'/'v6_tasks.json',[]):
  if z.get('local_qc_pass') is True and z.get('kind') in ('MERIT_FINAL80_SINGLE_TILE','MERIT_BUFFER_CONVERGENCE') and z.get('halo_km')==80:
   done.add(z.get('base_tile_key'))
 v7cost=core.read_json(f['v7']/'reports'/'v7_live_reconciliation_and_cost.json')
 if v7cost and v7cost.get('status')=='EIGHT_LIVE_TASKS_AND_LOCAL_FILES_VERIFIED':
  for z in v7cost['tasks']:
   if z.get('family')=='merit' and z.get('state')=='SUCCEEDED' and z.get('local_qc_pass'):
    done.add(str(z['key']).replace('merit_final80_',''))
 if not done:raise ValueError('No proven v6/v7 MERIT accepted block source; inspect real task evidence')
 missing=done-set(plan.tile_key)
 if missing:raise ValueError('Accepted MERIT sources do not match any v4 safe tile: '+str(missing))
 remain=plan.loc[~plan.tile_key.isin(done)].copy()
 remain['batch_id']='M8_'+remain.tile_key.astype(str)
 remain['source_family']='MERIT_HYDRO_16_BANDS_80KM_BUFFER'
 quarantine=pd.read_csv(f['v4']/'plans'/'merit_quarantine_v4.csv')
 if len(quarantine)!=14:raise ValueError('Expected 14 quarantined meridian blocks')
 return remain,quarantine
