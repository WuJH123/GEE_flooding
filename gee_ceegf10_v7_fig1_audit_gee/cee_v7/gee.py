"""Bounded GF10 x UTC proxy-day Earth Engine IMERG/ERA5-Land exports and independent CSV QC.

No Earth Engine task is submitted without --execute and exact immutable run ID.
This is *not* independent flood truth; output is weather exposure with source date uncertainty.
"""
from __future__ import annotations
import csv,datetime as dt,json,os,pathlib
import pandas as pd
from . import core

RUN_ID=core.NAME
CSV_FIELDS=['grid_id','date_utc','imerg_day_mm','imerg_peak_30min_mm_h',
'imerg_rolling3h_max_mm','imerg_pre7d_mm','imerg_pre14d_mm','imerg_pre30d_mm',
'imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre14d','imerg_n_obs_pre30d',
'era5_soil_l1_prevday_m3m3','era5_soil_l2_prevday_m3m3',
'era5_t2m_prevday_C','era5_rain_prevday_mm','era5_runoff_prevday_mm',
'era5_u_prevday_ms','era5_v_prevday_ms','era5_wind_prevday_ms']


def _paths(root):
    root=pathlib.Path(root)
    return root/'reports'/'v7_weather_tasks.json',root/'plans'/'gee_weather_date_tile_plan.csv',root/'plans'/'unique_GF10_UTC_proxy_days.parquet'

def _ledger(path):return core.read_json(path,[])

def preflight(root,grid_path,v6_root,plan_path=None,dates_path=None,strict=True):
    import pyarrow.parquet as pq
    root=pathlib.Path(root);ledger,plan_default,dates_default=_paths(root)
    plan=pathlib.Path(plan_path or plan_default);days=pathlib.Path(dates_path or dates_default)
    if not plan.is_file() or not days.is_file():raise FileNotFoundError('No audited pre-extraction plan. Run v7 cohort-plan first')
    qc=core.read_json(plan.parent/'cohort_and_weather_plan_qc.json')
    if not qc or qc.get('status')!='PREEXTRACT_ONLY_CASES_AND_UNLABELED_CANDIDATES':raise ValueError('No frozen candidate plan QC')
    if qc.get('frozen_grid_sha256')!=core.digest(grid_path):raise ValueError('GF10 changed since plan')
    core.check_grid(grid_path,strict=strict)
    if not pathlib.Path(v6_root).is_dir():raise FileNotFoundError('Accepted v6 source directory required')
    sg=core.read_json(pathlib.Path(v6_root)/'reports'/'merit_halo_science_gate_v6.json')
    if sg and sg.get('status') not in ('PASS_20_40_80_HALO_NUMERIC_CONVERGENCE',):
        raise ValueError('V6 MERIT science gate status abnormal')
    if not sg:
        raise FileNotFoundError('V6 accepted MERIT scientific gate missing; preserve existing v6')
    return {'status':'WEATHER_PREEXTRACT_PLAN_READY_NO_CLOUD_JOB',
      'project':core.PROJECT,'run_id':RUN_ID,'n_requests':int(len(pd.read_csv(plan))),
      'n_unique_days':int(pq.ParquetFile(days).metadata.num_rows),
      'gf10_sha256':core.digest(grid_path),'plan_sha256':core.digest(plan),
      'event_grid_day_sha256':core.digest(days),'v6_merit_science_gate':sg['status'],
      'complete_verified_no_flood_labels':False,'dates_are_UTC_proxy':True}


def _ee_init():
    try:import ee
    except ImportError as ex:raise RuntimeError('pip install earthengine-api before --execute') from ex
    ee.Initialize(project=core.PROJECT)
    return ee


def task_state(ee,rec):
    if not rec.get('operation'):
        return {'state':'INTENT_NOT_RECONCILED','eecu_h':None,'error':None}
    op=ee.data.getOperation(rec['operation'])
    meta=op.get('metadata') or {}
    usage=meta.get('batchEecuUsageSeconds',meta.get('batch_eecu_usage_seconds'))
    return {'state':meta.get('state','UNKNOWN'),
        'eecu_h':float(usage)/3600 if usage is not None else None,
        'error':(op.get('error') or {}).get('message')}


def select_request(root,key):
    _,plan_path,days_path=_paths(root)
    p=pd.read_csv(plan_path)
    if p.request_key.duplicated().any():raise ValueError('Duplicate weather request key')
    row=p[p.request_key.eq(key)]
    if len(row)!=1:raise KeyError('Unknown/missing date-tile request '+str(key))
    rows=pd.read_parquet(days_path)
    request=rows[rows.request_key.eq(key)].copy()
    expected=int(row.iloc[0].n_grid_days)
    if len(request)!=expected or not 1<=len(request)<=100:raise ValueError('Inconsistent frozen GF10 request membership')
    if request.grid_id.duplicated().any() or request.date_utc.nunique()!=1:raise ValueError('Invalid multi-day task')
    d=core.day_str(request.date_utc.iloc[0])
    if not d or d>core.PERMANENT_END or d<'2000-01-31':
        raise ValueError('Outside complete 30-day window of permanent IMERG V07')
    return row.iloc[0],request


def _make_task(ee,request,wkt,model):
    day=request.date_utc.iloc[0]
    feats=[]
    # Borrow the verified v4 anti-meridian projection constraint.
    from pyproj import Transformer
    to6933=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    west=to6933.transform(-180,0)[0];east=to6933.transform(180,0)[0]
    for v in request.itertuples(index=False):
        x=int(v.grid_x);y=int(v.grid_y)
        corners=[x*10000,y*10000,(x+1)*10000,(y+1)*10000]
        if corners[0]<west+1 or corners[2]>east-1:
            raise ValueError('GF10 antimeridian seam cell must be quarantined, never submit wrapped polygon')
        geom=ee.Geometry.Rectangle(corners,proj=wkt,geodesic=False)
        feats.append(ee.Feature(geom,{'grid_id':str(v.grid_id),'date_utc':str(day)}))
    fc=ee.FeatureCollection(feats)
    # Official IMERG V07 ~0.1 degree and ERA5-Land ~0.1 degree; do not claim
    # meteorology becomes independent native 10km observation by aggregation.
    # Explicit source-scale area-weighted means of small GF10 polygons.
    img=model.event_image(ee,day)
    result=img.reduceRegions(collection=fc,reducer=ee.Reducer.mean(),
                             crs='EPSG:4326',scale=11132,tileScale=4)
    return result


def submit(root,grid_path,v6_root,v3_path,key,execute=False,confirm=None,
           pilot_limit=3,live_cap=2,ready_cap=8,max_eecu_h=0.5):
    root=pathlib.Path(root);ledger,_,_=_paths(root)
    check=preflight(root,grid_path,v6_root)
    row,req=select_request(root,key)
    current=_ledger(ledger)
    if any(z['key']==key for z in current):raise ValueError('Already registered; reconcile GEE before re-submitting')
    details={'key':key,'date_utc':str(row.date_utc),'n_GF10':len(req),
             'run_id':RUN_ID,'project':core.PROJECT,'dry_run':not execute,
             'policy':'only UTC calendar proxy, NOT physical exact flood day',
             'IMERG':'NASA/GPM_L3/IMERG_V07 permanent',
             'ERA5':'ECMWF/ERA5_LAND/DAILY_AGGR previous day','pilot_only':True}
    if not execute:return details
    if confirm!=RUN_ID:raise ValueError('Explicit exact immutable --confirm run ID required')
    if sum(z.get('kind')=='WEATHER_PREEXTRACTION' for z in current)>=pilot_limit:
        raise ValueError('Pilot task limit; do not launch global date plan')
    ee=_ee_init()
    states=[task_state(ee,z) for z in current]
    if any(s['state']=='INTENT_NOT_RECONCILED' for s in states):raise ValueError('Unreconciled submit intent blocks all jobs')
    active=sum(s['state'] in ('RUNNING','READY','SUBMITTED','PENDING') for s in states)
    if active>=live_cap+ready_cap:raise ValueError('GEE queue limit reached')
    spent=sum(float(s['eecu_h']) for s in states if s['eecu_h'] is not None)
    if spent>=max_eecu_h or spent+0.15>max_eecu_h:raise ValueError('GEE v7 pilot budget exhausted')
    # Import EXACT frozen v3 model, not an altered unvalidated collection.
    import sys
    path=pathlib.Path(v3_path)
    if not path.is_dir():raise FileNotFoundError('Validated v3 model required')
    sys.path.insert(0,str(path))
    from ceeprodgee import ee_model
    cfg=core.read_json(path/'config'/'production.json')
    if cfg is None or cfg.get('project')!=core.PROJECT or not cfg.get('pilot_merit_passed'):
        raise ValueError('Upstream verified v3 not locked')
    wkt=cfg['output_crs_wkt']
    collection=_make_task(ee,req,wkt,ee_model)
    desc=RUN_ID+'_'+key
    task=ee.batch.Export.table.toDrive(collection=collection,description=desc,
       folder='CEE_GF10_FIG1_AUDITED_WEATHER_V7_20261106',fileNamePrefix=desc,
       fileFormat='CSV',selectors=CSV_FIELDS)
    record={'kind':'WEATHER_PREEXTRACTION','key':key,'task_id':task.id,
      'operation':None,'state':'SUBMISSION_INTENT','project':core.PROJECT,
      'request_sha256':core.digest(_paths(root)[2]),'plan_sha256':check['plan_sha256'],
      'date_utc':str(row.date_utc),'n_expected_rows':len(req),
      'filename':desc+'.csv','local_qc_pass':False,'source_date_is_UTC_proxy':True,
      'created_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    core.write_json(ledger,current+[record],replace=True)
    task.start()
    st=task.status()
    record['operation']=st.get('name') or f'projects/{core.PROJECT}/operations/{task.id}'
    record['state']=st.get('state','SUBMITTED')
    core.write_json(ledger,current+[record],replace=True)
    return {**details,'dry_run':False,'task_id':task.id,'operation':record['operation'],
      'next':'Wait for SUCCEEDED, download exact Drive CSV, run weather-audit then live-accept'}


def status(root):
    ledger=_paths(root)[0];records=_ledger(ledger)
    if not records:return {'status':'NO_GEE_WEATHER_TASKS'}
    ee=_ee_init();res=[];total=0.;missing=[]
    for rec in records:
        st=task_state(ee,rec)
        if st['eecu_h'] is not None:total+=st['eecu_h']
        else:missing.append(rec['key'])
        res.append({'key':rec['key'],'task_id':rec.get('task_id'),'operation':rec.get('operation'),
                    **st,'local_qc_pass':rec.get('local_qc_pass')})
    return {'status':'LIVE_GEE_CHECK','tasks':res,'known_eecu_h':total,
            'tasks_with_unknown_eecu':missing}


def audit(root,key,csv_path,strict_valid_rows=False):
    import numpy as np
    root=pathlib.Path(root);ledger,_,days_path=_paths(root)
    records=_ledger(ledger);hits=[z for z in records if z['key']==key]
    if len(hits)!=1:raise ValueError('Unknown registered task')
    rec=hits[0]
    live=task_state(_ee_init(),rec)
    if live['state'] not in ('SUCCEEDED','COMPLETED'):
        raise ValueError('GEE operation has not SUCCEEDED')
    p=pathlib.Path(csv_path)
    if p.name!=rec['filename']:
        raise ValueError('Exported filename does not match frozen task')
    data=pd.read_csv(p)
    if not set(CSV_FIELDS)<=set(data):raise ValueError('Required source weather fields missing: '+str(set(CSV_FIELDS)-set(data)))
    d=pd.read_parquet(days_path,columns=['request_key','grid_id','date_utc'])
    d=d[d.request_key.eq(key)][['grid_id','date_utc']]
    data.grid_id=data.grid_id.astype(str);d.grid_id=d.grid_id.astype(str)
    data.date_utc=data.date_utc.astype(str)
    if data.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate GEE weather keys')
    merged=d.merge(data,on=['grid_id','date_utc'],how='left',indicator=True,validate='one_to_one')
    if len(data)!=len(d) or not merged['_merge'].eq('both').all():raise ValueError('Missing/extra GF10 days in CSV')
    for b in CSV_FIELDS[2:]:merged[b]=pd.to_numeric(merged[b],errors='coerce')
    nc=['imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre14d','imerg_n_obs_pre30d']
    good=merged[nc].notna().all(axis=1)
    for c,n in zip(nc,[48,336,672,1440]):good &= merged[c].ge(n-0.001)&merged[c].le(n+0.001)
    rain=['imerg_day_mm','imerg_rolling3h_max_mm','imerg_pre7d_mm','imerg_pre14d_mm',
          'imerg_pre30d_mm','era5_rain_prevday_mm']
    good &= merged[rain].notna().all(axis=1)&merged[rain].ge(-0.01).all(axis=1)
    good &= merged['imerg_rolling3h_max_mm'].le(merged['imerg_day_mm']+0.01)
    soil=['era5_soil_l1_prevday_m3m3','era5_soil_l2_prevday_m3m3']
    good &= merged[soil].notna().all(axis=1)&merged[soil].ge(-0.001).all(axis=1)&merged[soil].le(1.001).all(axis=1)
    good &= merged['era5_t2m_prevday_C'].notna() & merged['era5_t2m_prevday_C'].between(-90,65)
    valid=int(good.sum());allgood=bool(good.all())
    if strict_valid_rows and not allgood:raise ValueError('Missing IMERG/ERA5 observations; do NOT substitute zero')
    report={'status':'LOCAL_CSV_AUDITED_GEE_SUCCEEDED_WITH_MISSINGNESS' if not allgood else 'LOCAL_CSV_QC_PASS',
       'key':key,'n_expected':len(d),'n_actual':len(data),'n_complete_valid':valid,
       'n_masked_or_incomplete':len(data)-valid,'csv_sha256':core.digest(p),'eecu_h':live['eecu_h'],
       'source_date_is_UTC_proxy':True,'source_is_reported_news_not_flood_truth':True,
       'no_flood_negatives_verified':False,'complete_row_coverage':allgood}
    rec['local_qc_pass']=allgood
    rec['source_csv_sha256']=core.digest(p);rec['eecu_h']=live['eecu_h'];rec['local_file']=str(p)
    core.write_json(ledger,records,replace=True)
    core.write_json(root/'reports'/('weather_'+key+'.qc.json'),report,replace=True)
    return report


def assemble(root,out_path):
    root=pathlib.Path(root);records=_ledger(_paths(root)[0]);ok=[r for r in records if r.get('local_qc_pass')]
    if not ok:raise ValueError('No real audited weather tasks')
    tables=[]
    for r in ok:
        if core.digest(r['local_file'])!=r['source_csv_sha256']:raise ValueError('Weather CSV changed since audit')
        tables.append(pd.read_csv(r['local_file'])[CSV_FIELDS])
    joined=pd.concat(tables,ignore_index=True)
    if joined.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate GF10 weather date')
    core.ensure_new(out_path);joined.to_parquet(out_path,index=False)
    report={'status':'VERIFIED_WEATHER_PARTIAL_ONLY','n_gf10_date_records':len(joined),
        'n_source_tasks_accepted':len(ok),'source_sha256':[r['source_csv_sha256'] for r in ok],
        'output_sha256':core.digest(out_path),'not_full_global_or_final_case_control':True}
    core.write_json(pathlib.Path(out_path).with_suffix('.qc.json'),report)
    return report
