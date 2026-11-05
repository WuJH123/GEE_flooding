"""V6 sidecar: real GEE halo pilots and preweather candidate date extraction.

No automatic 16,860-task batch, no re-submission of accepted old jobs.
All calls require frozen v4 config and an explicit --execute+--confirm.
"""
from __future__ import annotations
import os,pathlib,json
from .common import ROOT,load,save,now,sha,PROJECT,FINAL_V07_END
from .science import buffered_geometry,BANDS,compare_rasters,approve
from .cohort import make_request_plan

CLOUD=ROOT/'reports'/'v6_tasks.json'
RUN_ID='CEE_GF10_MERIT_M0_SCIENCE_V6_20261105'

def old_context(root):
    r=pathlib.Path(root)
    v4=r/'CEE_GF10_GEE_RECOVERY_V4_20261105'
    v5=r/'CEE_GF10_GEE_PRODUCTION_V5'
    if not v4.is_dir():
        v4=r/'CEE_GF10_GEE_RECOVERY_V4_1_20261105'
    cf=v4/'config'/'recovery.json'
    if not cf.exists():raise FileNotFoundError('Existing, accepted v4 recovery.json required: '+str(cf))
    c=load(cf)
    if c.get('project')!=PROJECT:raise ValueError('Wrong GEE project: no new project authorized')
    if c.get('grid_sha256')!='4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d':
        raise ValueError('GF10 sha does not match verified v5 preflight')
    return r,v4,v5,c

def init_ee(c):
    import ee
    ee.Initialize(project=c['project'])
    return ee

def limits():
    from pyproj import Transformer
    tr=Transformer.from_crs(4326,6933,always_xy=True)
    left,_=tr.transform(-180,0);right,_=tr.transform(180,0)
    _,low=tr.transform(0,-86);_,hi=tr.transform(0,86)
    return left,right,low,hi

def safe_record(c, root, key):
    import pandas as pd
    r,v4,v5,_=old_context(root)
    path=v4/'plans'/'merit_safe_v4.csv'
    if not path.exists():raise FileNotFoundError(path)
    p=pd.read_csv(path)
    rows=p[p.tile_key.eq(key)]
    if len(rows)!=1:raise ValueError('Not a unique safe MERIT tile: '+key)
    row=rows.iloc[0];x=int(row.crop_x0);y=int(row.crop_y0)
    w=int(row.width);h=int(row.height)
    if w<1 or h<1 or w*h>100:raise ValueError('Invalid compact 10km shape')
    bbox=[x*10000,y*10000,(x+w)*10000,(y+h)*10000]
    return row,bbox

def _old_accepted_keys(root):
    import pandas as pd
    r,v4,v5,c=old_context(root)
    accepted=set()
    path=v5/'reports'/'v5_existing_accepted.csv'
    if path.exists():
        f=pd.read_csv(path)
        if not {'tile_key','science_status','sha256'}.issubset(f):raise ValueError('V5 accepted registry invalid')
        accepted.update(f.tile_key.astype(str))
    old=v4/'reports'/'recovery_tasks.json'
    if old.exists():
        for z in load(old):
            if z.get('local_qc_pass') is True:accepted.add(z['key'])
    return accepted

def _reconcile_ledger(ee,ledger):
    for item in ledger:
        if item.get('operation') is None:raise RuntimeError('Unreconciled SUBMISSION_INTENT: do not re-submit automatically')
        z=ee.data.getOperation(item['operation'])
        st=(z.get('metadata') or {}).get('state','UNKNOWN')
        if st in ('READY','RUNNING','PENDING','UNKNOWN'):
            raise RuntimeError('Previous task still unresolved: '+item['key']+' '+st)
        if st not in ('SUCCEEDED','COMPLETED') or not item.get('local_qc_pass'):
            raise RuntimeError('Previous task not accepted: '+item['key']+' '+st)
    return True

def _register_task(ee,c,key,out_name,export,fields):
    records=load(CLOUD) if CLOUD.exists() else []
    if any(z['key']==key for z in records):raise RuntimeError('Duplicate new task key')
    _reconcile_ledger(ee,records)
    # CEE project-level EECU status is still independently verified per pilot;
    # do not use the last successful 2x2 result as a global rate forecast.
    verified=[]
    for prev in records:
        op=ee.data.getOperation(prev['operation']);meta=op.get('metadata') or {}
        eecu=meta.get('batchEecuUsageSeconds',meta.get('batch_eecu_usage_seconds'))
        if eecu is None:raise RuntimeError('Previous EECU cost unavailable: close budget gate')
        verified.append(float(eecu)/3600)
    if sum(verified)+.25>5.0:raise RuntimeError('V6 science pilot hard-stop at 5 EECU-hours; no automatic increase')
    task=export
    entry={'key':key,'file':out_name,'operation':None,'task_id':task.id,
           'status':'SUBMISSION_INTENT','project':PROJECT,'run_id':RUN_ID,
           'created_utc':now(),'local_qc_pass':False,**fields}
    save(CLOUD,records+[entry],overwrite=True)
    task.start();s=task.status()
    entry['operation']=s.get('name') or f'projects/{PROJECT}/operations/{task.id}'
    entry['status']=s.get('state','UNKNOWN')
    save(CLOUD,records+[entry],overwrite=True)
    return entry

def static_halo_submit(root,key,halo_km,execute=False,confirm=None):
    if halo_km not in (20,40,80):raise ValueError('Supported science calibration halos: 20, 40, 80km')
    _,v4,v5,c=old_context(root)
    row,bbox=safe_record(c,root,key)
    calc,export=buffered_geometry(bbox,halo_km,limits())
    ident=f'halo{halo_km}_{key}'
    preview={'status':'DRY_RUN_NO_GEE' if not execute else 'SUBMISSION_REQUESTED',
             'key':ident,'calc_bounds_m':calc,'export_center_envelope_m':export,
             'n_expected_pixels':int(row.width*row.height),'n_land_cells':int(row.n_land_cells)}
    if not execute:return preview
    if confirm!=RUN_ID:raise ValueError('Exact v6 run id confirmation required')
    if key in _old_accepted_keys(root) and halo_km==0:raise ValueError('Original already accepted tile; do not re-submit')
    from ceeprodgee import ee_model
    ee=init_ee(c)
    roi=ee.Geometry.Rectangle(calc,proj=c['crs_wkt'],geodesic=False)
    exp_region=ee.Geometry.Rectangle(export,proj=c['crs_wkt'],geodesic=False)
    image=ee_model.merit(ee,roi,c['crs_wkt']).unmask(-9999)
    basename=f'{RUN_ID}_{ident}'
    task=ee.batch.Export.image.toDrive(image=image,description=basename,
           folder=RUN_ID,fileNamePrefix=basename,region=exp_region,crs=c['crs_wkt'],
           crsTransform=ee_model.TRANSFORM_10,maxPixels=200,fileFormat='GeoTIFF',
           formatOptions={'cloudOptimized':True,'noData':-9999})
    rec=_register_task(ee,c,ident,basename+'.tif',task,
        {'kind':'MERIT_BUFFER_CONVERGENCE','base_tile_key':key,'halo_km':halo_km,
         'crop':[int(row.crop_x0),int(row.crop_y0),int(row.width),int(row.height)],
         'source_contract':list(BANDS),'gf10_sha256':c['grid_sha256']})
    return rec


def static_production_submit(root,key,execute=False,confirm=None,
                             recalibrate_legacy=False,reason=None):
    """Submit ONE safe final buffered block; never a large unapproved loop.

    Requires an independent three-climate, 16-band 40-vs-80 km halo gate.
    The source v5 FAIL remains intact; this produces new v6 evidence only.
    """
    gate=ROOT/'reports'/'merit_halo_science_gate_v6.json'
    if not gate.is_file() or load(gate).get('status')!='PASS_20_40_80_HALO_NUMERIC_CONVERGENCE':
        raise RuntimeError('Global MERIT submission blocked until 3-climate 40/80 km halo convergence passes')
    existing=key in _old_accepted_keys(root)
    if existing and not recalibrate_legacy:
        raise ValueError('Legacy engineering-accepted tile is not science-equivalent; requires explicit --recalibrate-legacy with documented reason, or reuse a separately verified 80km halo product')
    if recalibrate_legacy and (not existing or not reason or len(reason.strip())<20):
        raise ValueError('Legacy recalibration only for historical engineering-accepted tiles and with >=20-char scientific justification')
    _,v4,v5,c=old_context(root)
    row,bbox=safe_record(c,root,key)
    calc,export=buffered_geometry(bbox,80,limits())
    ident='merit_final80_'+key
    report={'status':'DRY_RUN_NO_GEE','key':ident,'input_bbox':bbox,'buffered_calc_bbox':calc,
            'export_bbox':export,'output_cells':int(row.width*row.height),'study_gate':sha(gate)}
    if not execute:return report
    if confirm!=RUN_ID:raise ValueError('Explicit immutable v6 run-id required')
    from ceeprodgee import ee_model
    ee=init_ee(c)
    roi=ee.Geometry.Rectangle(calc,proj=c['crs_wkt'],geodesic=False)
    output=ee.Geometry.Rectangle(export,proj=c['crs_wkt'],geodesic=False)
    img=ee_model.merit(ee,roi,c['crs_wkt']).unmask(-9999)
    basename=f'{RUN_ID}_{ident}'
    task=ee.batch.Export.image.toDrive(image=img,description=basename,folder=RUN_ID,
            fileNamePrefix=basename,region=output,crs=c['crs_wkt'],
            crsTransform=ee_model.TRANSFORM_10,maxPixels=200,fileFormat='GeoTIFF',
            formatOptions={'cloudOptimized':True,'noData':-9999})
    return _register_task(ee,c,ident,basename+'.tif',task,
             {'kind':'MERIT_FINAL80_SINGLE_TILE','base_tile_key':key,'halo_km':80,
              'crop':[int(row.crop_x0),int(row.crop_y0),int(row.width),int(row.height)],
              'legacy_recalibration':bool(recalibrate_legacy),'legacy_recalibration_reason':reason,
              'gf10_sha256':c['grid_sha256'],'science_gate_sha256':sha(gate),
              'source_contract':list(BANDS)})

def request_submit(root,request_key,execute=False,confirm=None):
    import pandas as pd
    r,v4,v5,c=old_context(root)
    plans=ROOT/'plans'/'event_requests_v6.csv'
    request_rows=ROOT/'plans'/'event_grid_days_v6.parquet'
    if not plans.exists() or not request_rows.exists():raise FileNotFoundError('Run v6 calendar cohort -> weather-request-plan first')
    plan=pd.read_csv(plans);row=plan[plan.request_key.eq(request_key)]
    if len(row)!=1:raise ValueError('Unknown/ambiguous weather request key: '+request_key)
    row=row.iloc[0]
    sample=pd.read_parquet(request_rows)
    pick=sample[(sample.date_utc==row.date_utc)&
         (sample.tile_x0==row.tile_x0)&(sample.tile_y0==row.tile_y0)]
    if len(pick)!=int(row.n_grid_days) or len(pick)>100:raise ValueError('Incomplete/malformed date×tile group')
    if not ('2021-01-01'<=str(row.date_utc)<='2025-09-30'):
        raise ValueError('Beyond 2025-09-30 IMERG V07 permanent record window')
    for f in pick.itertuples(index=False):
        bbox=[int(f.grid_x)*10000,int(f.grid_y)*10000,(int(f.grid_x)+1)*10000,(int(f.grid_y)+1)*10000]
        buffered_geometry(bbox,0,limits()) # same GF10 land source, seam controlled
    result={'status':'DRY_RUN_NO_GEE','key':request_key,'date_utc':str(row.date_utc),
            'n_sample_grid_days':len(pick),'note':'Preweather candidate extraction, NOT matched flood-negative cohort'}
    if not execute:return result
    if confirm!=RUN_ID:raise ValueError('Explicit immutable confirmation required')
    from ceeprodgee import ee_model
    ee=init_ee(c)
    features=[]
    for f in pick.itertuples(index=False):
        box=[int(f.grid_x)*10000,int(f.grid_y)*10000,(int(f.grid_x)+1)*10000,(int(f.grid_y)+1)*10000]
        geo=ee.Geometry.Rectangle(box,proj=c['crs_wkt'],geodesic=False)
        features.append(ee.Feature(geo,{'grid_id':str(f.grid_id),'date_utc':str(row.date_utc)}))
    img=ee_model.event_image(ee,str(row.date_utc))
    # Batch each date+GF10 tile once; no simulated zero ERA5 values on marine cells.
    samples=img.reduceRegions(collection=ee.FeatureCollection(features),reducer=ee.Reducer.mean(),
          crs=c['crs_wkt'],crsTransform=ee_model.TRANSFORM_10,tileScale=4)
    basename=f'{RUN_ID}_{request_key}'
    task=ee.batch.Export.table.toDrive(collection=samples,description=basename,
         folder=RUN_ID,fileNamePrefix=basename,fileFormat='CSV')
    return _register_task(ee,c,request_key,basename+'.csv',task,
        {'kind':'PRE_WEATHER_SCREENING','n_grid_days':len(pick),
         'tile_x0':int(row.tile_x0),'tile_y0':int(row.tile_y0),
         'date_utc':str(row.date_utc),'inputs_sha256':sha(request_rows),
         'rain_source':'NASA/GPM_L3/IMERG_V07_permanent',
         'era5_source':'ECMWF/ERA5_LAND/DAILY_AGGR'})

def inspect_task_status(root):
    _,_,_,c=old_context(root)
    records=load(CLOUD) if CLOUD.exists() else []
    if not records:return {'status':'NO_V6_GEE_TASKS','n':0}
    ee=init_ee(c);summary=[]
    for z in records:
        if z.get('operation') is None:
            summary.append({'key':z['key'],'state':'UNRESOLVED_INTENT'});continue
        op=ee.data.getOperation(z['operation']);meta=op.get('metadata') or {}
        sec=meta.get('batchEecuUsageSeconds',meta.get('batch_eecu_usage_seconds'))
        summary.append({'key':z['key'],'state':meta.get('state','UNKNOWN'),
                        'eecu_h':float(sec)/3600 if sec is not None else None,
                        'local_qc_pass':z['local_qc_pass'],
                        'error':(op.get('error') or {}).get('message')})
    return {'status':'READ_ONLY_LIVE_TASK_STATUS','tasks':summary}

def audit_halo(key,local_tif):
    import rasterio
    recs=load(CLOUD)
    rows=[z for z in recs if z['key']==key]
    if len(rows)!=1:raise ValueError('Unknown exact task')
    z=rows[0]
    if z['kind'] not in ('MERIT_BUFFER_CONVERGENCE','MERIT_FINAL80_SINGLE_TILE'):raise ValueError('Not MERIT')
    xx,yy,w,h=z['crop'];p=pathlib.Path(local_tif)
    with rasterio.open(p) as src:
        tf=src.transform
        if src.crs.to_epsg()!=6933 or (src.width,src.height,src.count)!=(w,h,16):
            raise ValueError('MERIT raster width/height/crs/bands not frozen')
        if any(abs(a-b)>1e-6 for a,b in zip(tuple(tf)[:6],(10000.,0.,float(xx*10000),0.,-10000.,float((yy+h)*10000)))):
            raise ValueError('MERIT exact affine transform mismatch')
    from ceeprodgee import qc
    check=qc.check_raster(p,'merit',xx,yy,w,expected_manifest=BANDS)
    # Do not mark QC_PASS only based on local file if EE terminal status is unverified.
    z['local_qc_pass']=False;z['local_file_sha256']=sha(p);z['raster_qc']=check
    z['local_qc_geometry_pass']=True
    save(CLOUD,recs,overwrite=True)
    return {'status':'GEOMETRY_QC_PASS_REQUIRES_LIVE_EE_AND_HALO_CONVERGENCE',
            'key':key,'sha256':z['local_file_sha256']}

def audit_weather(root,key,file):
    import pandas as pd
    records=load(CLOUD)
    rows=[z for z in records if z['key']==key and z['kind']=='PRE_WEATHER_SCREENING']
    if len(rows)!=1:raise ValueError('Unknown weather task key')
    z=rows[0];src=pd.read_csv(file)
    required={'grid_id','date_utc','imerg_day_mm','imerg_rolling3h_max_mm',
              'imerg_pre7d_mm','imerg_pre30d_mm','imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre30d'}
    if not required.issubset(src.columns):raise ValueError('GEE CSV missing source bands '+str(required-set(src.columns)))
    req=pd.read_parquet(ROOT/'plans'/'event_grid_days_v6.parquet')
    expect=req[(req.date_utc==z['date_utc'])&(req.tile_x0==z['tile_x0'])&
               (req.tile_y0==z['tile_y0'])][['grid_id','date_utc']]
    actual=src[['grid_id','date_utc']].copy().astype(str)
    if src.duplicated(['grid_id','date_utc']).any() or len(src)!=z['n_grid_days']:
        raise ValueError('Duplicate or missing GEE event grid-days')
    if not set(map(tuple,actual.values))==set(map(tuple,expect.astype(str).values)):
        raise ValueError('Observed GEE grid/date keys do not match frozen request')
    for n,expected in [('imerg_n_obs_day',48),('imerg_n_obs_pre7d',336),('imerg_n_obs_pre30d',1440)]:
        if (src[n].fillna(-1)>expected).any():raise ValueError('IMERG observed count exceeds temporal window '+n)
    bad=(~src.imerg_n_obs_day.eq(48)|~src.imerg_n_obs_pre7d.eq(336)|~src.imerg_n_obs_pre30d.eq(1440))
    for name in ('imerg_day_mm','imerg_pre7d_mm','imerg_pre30d_mm'):
        if src.loc[~bad,name].isna().any():raise ValueError('Complete rain count but null rainfall '+name)
    z['local_qc_pass']=False # separate EE SUCCEEDED verification gate below
    z['local_qc_geometry_pass']=True;z['local_file_sha256']=sha(file)
    save(CLOUD,records,overwrite=True)
    report={'status':'CSV_KEYS_COUNTS_PASS_PENDING_LIVE_TASK_VERIFICATION',
       'n_rows':len(src),'n_missing_imerghh':int(bad.sum()),
       'n_missing_era5_soil':int(src.get('era5_soil_l1_prevday_m3m3',pd.Series([None]*len(src))).isna().sum()),
       'csv_sha256':z['local_file_sha256'],'not_confirmed_dry':True}
    save(ROOT/'reports'/(key+'.weather_qc.json'),report)
    return report

def live_accept(root,key):
    _,_,_,c=old_context(root)
    records=load(CLOUD);matches=[z for z in records if z['key']==key]
    if len(matches)!=1:raise ValueError('Unknown task')
    z=matches[0]
    if not z.get('local_qc_geometry_pass') or not z.get('local_file_sha256'):
        raise ValueError('Download first and run local numeric/row/geometry audit')
    ee=init_ee(c)
    op=ee.data.getOperation(z['operation']);m=op.get('metadata') or {}
    state=m.get('state','UNKNOWN');sec=m.get('batchEecuUsageSeconds',m.get('batch_eecu_usage_seconds'))
    if state not in ('SUCCEEDED','COMPLETED') or sec is None:raise ValueError('Task not verified terminal success with reported EECU')
    z['local_qc_pass']=True;z['eecu_h']=float(sec)/3600
    save(CLOUD,records,overwrite=True)
    return {'status':'LIVE_TASK_AND_LOCAL_QC_ACCEPTED','key':key,'eecu_h':z['eecu_h']}
