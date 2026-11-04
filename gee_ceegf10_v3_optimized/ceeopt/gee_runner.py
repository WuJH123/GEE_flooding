"""Single-task budget-gated MERIT and unique-grid-date meteorology exports.

No task submission without explicit --execute and exact confirm token.
No access to other GEE projects beyond a user-authored frozen local_run.json.
"""
from __future__ import annotations
import json,math,datetime as dt,hashlib
from pathlib import Path
from .base import load_json,atomic_json,sha256,load_gf10,M1_FIELDS,GRID_N,utc_now
from .cost import projected_hours,MERIT_EECU_400
from .weather import event_image,validated_date,METEO_BANDS,validate_weather_raster,make_event_plan

BASE=Path(__file__).resolve().parents[1]
RUN_ID='CEE_GF10_OPTIMIZED_V3_20261104'
STATIC_LEDGER=BASE/'reports'/'merit_task_ledger.json'
EVENT_LEDGER=BASE/'reports'/'weather_task_ledger.json'


def _root():
    # Source project path is supplied only by a local config from prior accepted run.
    cfg=BASE/'config'/'runtime.json'
    x=load_json(cfg)
    if x:return x
    base=BASE.parent
    old=base/'gee_ceegf10_v1'/'config'/'local_run.json'
    if not old.is_file():
        raise FileNotFoundError(f'No previous verified independent GEE project config: {old}')
    d=load_json(old)
    g=Path(d['grid'])
    load_gf10(g,True)
    out={'project':d['project'],'gf10':str(g),'gf10_sha256':sha256(g),'run_id':RUN_ID,
         'drive_folder':RUN_ID,'budget_merit_h':700,'last_final_imerg_day':'2025-09-30'}
    atomic_json(cfg,out)
    return out

def _ee():
    import ee
    c=_root()
    ee.Initialize(project=c['project'])
    return ee

def _wkt():
    from pyproj import CRS
    return CRS.from_epsg(6933).to_wkt(version='WKT1_GDAL')

def _task_status(ee,record):
    from ceeprodgee.ledger import task_state
    if not record.get('operation'):raise RuntimeError('Missing task operation identifier')
    return task_state(ee,record['operation'])

def _ledger_status(ee,filename):
    rows=load_json(filename,[])
    for row in rows:
        status=_task_status(ee,row)
        row.update(status)
    atomic_json(filename,rows)
    return rows

def source_probe():
    """Read-only, bounded catalog metadata; no exports or external assets."""
    e=_ee()
    data={'project':_root()['project'],'source_bands':{
        'merit':e.Image('MERIT/Hydro/v1_0_1').bandNames().getInfo(),
        'worldcover':e.ImageCollection('ESA/WorldCover/v200').first().bandNames().getInfo(),
        'imerg':e.ImageCollection('NASA/GPM_L3/IMERG_V07').first().bandNames().getInfo(),
        'era5':e.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').first().bandNames().getInfo()}}
    need={'merit':{'hnd','elv','upa','wat'},'worldcover':{'Map'},
          'imerg':{'precipitation'},
          'era5':{'temperature_2m','total_precipitation_sum','volumetric_soil_water_layer_1','volumetric_soil_water_layer_2'}}
    for family,expect in need.items():
        missing=expect-set(data['source_bands'][family]);
        if missing:raise ValueError(f'{family}: missing official bands {sorted(missing)}')
    atomic_json(BASE/'reports'/'gee_source_probe.json',data)
    return data

def merit_tile_origin(x,y,block=20):
    """Pre-registered 20-cell task lattice: offset x by 10 GF10 cells."""
    if block not in (10,20):raise ValueError('MERIT block must be 10 or 20')
    xo=10 if block==20 else 0
    return ((int(x)-xo)//block*block+xo,int(y)//block*block)


def merit_plan(block=20):
    import pandas as pd
    from ceeprodgee.grid import make_plan
    if block not in (10,20):raise ValueError('MERIT block size 10 or 20; 20 needs online Gate-C equivalence approval')
    g=load_gf10(_root()['gf10'],True)
    x=g[['grid_id','grid_x','grid_y','land_area_km2']].copy()
    # Anchor 20x20 MERIT tiles at x = ...,-10,10,30,... so the entire
    # already-validated Wuhan Gate C 1097..1106 block lies inside ONE
    # aligned 20x20 production tile (1090,360), avoiding pilot duplication.
    xoffset=10 if block==20 else 0
    x['bx']=((x.grid_x-xoffset)//block)*block+xoffset
    x['by']=(x.grid_y//block)*block
    p=(x.groupby(['bx','by'],sort=True).agg(n_land_cells=('grid_id','size'),
                  km2_land=('land_area_km2','sum')).reset_index())
    p['tile_size']=block;p['key']=[f'merit_{xx}_{yy}_{block}' for xx,yy in zip(p.bx,p.by)]
    path=BASE/'plans'/f'merit_{block}_all.csv';path.parent.mkdir(parents=True,exist_ok=True)
    p.to_csv(path,index=False)
    atomic_json(path.with_suffix('.meta.json'),{'grid_sha':_root()['gf10_sha256'],
             'plan_sha256':sha256(path),'n_blocks':len(p),'covered_grid':int(p.n_land_cells.sum()),
             'note':'20x20 after exact independent Gate C validation only; tasks are NOT submitted by plan'})
    return {'path':str(path),'n_tasks':len(p),'n_grid':int(p.n_land_cells.sum()),
            'eecu_base_scenario':round(projected_hours(GRID_N,MERIT_EECU_400),1)}

def _checked_plan(path):
    import pandas as pd
    p=Path(path);meta=load_json(p.with_suffix('.meta.json'))
    if not meta or sha256(p)!=meta['plan_sha256'] or meta['grid_sha']!=_root()['gf10_sha256']:
        raise ValueError('Frozen plan checksum mismatch; do not submit altered batches')
    df=pd.read_csv(p)
    return df

def merit_submit(plan=None,pilot=False,execute=False,confirm=None):
    from ceeprodgee.ee_model import merit,TRANSFORM_10
    if not execute:return {'status':'DRY_RUN','note':'No Earth Engine task submitted. Use --execute with exact --confirm.'}
    if confirm!=RUN_ID:raise ValueError('Exact CEE v3 run id confirmation required')
    c=_root();ee=_ee()
    registry=_ledger_status(ee,STATIC_LEDGER)
    # No simultaneous uncontrolled exports, especially after a failed task.
    if any(r['state'] not in ('SUCCEEDED','COMPLETED') or not r.get('local_qc_pass',False) for r in registry):
        raise RuntimeError('Previous MERIT task incomplete/unaudited. First status, download TIFF and audit.')
    if pilot:
        # A 20x20 pilot covers the original Gate-C Wuhan 10x10 reference.
        x,y,n=1090,360,20
    else:
        if not plan:raise ValueError('Provide immutable --plan path')
        df=_checked_plan(plan)
        if df.empty:raise ValueError('Plan empty')
        submitted={r['key'] for r in registry}
        candidates=df.loc[~df.key.isin(submitted)]
        if candidates.empty:return {'status':'ALL_PLAN_TASKS_SUBMITTED','note':'Still audit all and merge; no new task'}
        row=candidates.iloc[0];x,y,n=int(row.bx),int(row.by),int(row.tile_size)
        if n==20 and not (BASE/'reports'/'merit_20_online_gate_pass.json').exists():
            raise RuntimeError('20x20 MERIT not proven online against original Gate C Wuhan; run pilot + audit first')
    from ceeprodgee.grid import tile_bounds
    key=f'merit_{x}_{y}_{n}'
    if any(r['key']==key for r in registry):raise ValueError('Task already submitted; no duplication')
    spent=0.0
    for r in registry:
        if r.get('eecu_hours') is None:raise RuntimeError('Task EECU unknown; budget review required')
        spent+=r['eecu_hours']
    scenario=projected_hours(n*n,MERIT_EECU_400)*5  # 5x per-task safety margin, not a guarantee
    if spent+scenario>=c['budget_merit_h']:
        raise RuntimeError('Current MERIT task budget guard exceeded; stop and review project-level EECU usage')
    roi=ee.Geometry.Rectangle(tile_bounds(x,y,n),proj=_wkt(),geodesic=False)
    img=merit(ee,roi,_wkt()).unmask(-9999)
    name=f'{RUN_ID}_{key}'
    task=ee.batch.Export.image.toDrive(image=img,description=name,folder=c['drive_folder'],
      fileNamePrefix=name,region=roi,crs=_wkt(),crsTransform=TRANSFORM_10,
      maxPixels=1e7,fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    task.start();stat=task.status()
    rec={'key':key,'family':'merit','pilot':pilot,'grid_x0':x,'grid_y0':y,'size':n,
         'file':name+'.tif','operation':stat.get('name') or f"projects/{c['project']}/operations/{task.id}",
         'task_id':task.id,'state':stat.get('state'),'local_qc_pass':False,
         'grid_sha':c['gf10_sha256'],'project':c['project'],'bands':list(M1_FIELDS),
         'submitted_utc':utc_now()}
    registry.append(rec);atomic_json(STATIC_LEDGER,registry)
    return rec

def merit_audit(key,file=None):
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from ceeprodgee.qc import check_raster
    c=_root();ee=_ee();rows=_ledger_status(ee,STATIC_LEDGER)
    matches=[r for r in rows if r['key']==key]
    if len(matches)!=1:raise ValueError('Task not found')
    z=matches[0]
    if z['state'] not in ('SUCCEEDED','COMPLETED'):raise RuntimeError('MERIT task not succeeded')
    path=Path(file) if file else BASE/'downloads'/z['file']
    check=check_raster(path,'merit',z['grid_x0'],z['grid_y0'],z['size'],expected_manifest=M1_FIELDS)
    if z.get('pilot'):
        ref=BASE.parent/'gee_ceegf10_v1'/'reports'/'gate_c_drive_tifs'/'gate_c_merit_v2_wuhan_10x10.tif'
        if not ref.is_file():raise FileNotFoundError('Missing independent original Gate C Wuhan MERIT GeoTIFF '+str(ref))
        with rasterio.open(ref) as r, rasterio.open(path) as v:
            # Exact same Wuhan reference window sampled from 20x20 tile.
            win=from_bounds(*r.bounds,transform=v.transform).round_offsets().round_lengths()
            if win.width!=10 or win.height!=10:raise ValueError('MERIT pilot cannot align Gate C Wuhan 10km data')
            a=r.read(masked=True).filled(np.nan)
            b=v.read(window=win,masked=True).filled(np.nan)
            both=np.isfinite(a)&np.isfinite(b)
            if both.sum()<100:raise ValueError('Insufficient independent MERIT pixels')
            delta=np.abs(a[both]-b[both])/np.maximum(1,np.abs(a[both]))
            check['merit_gate_c_relative_p95']=float(np.percentile(delta,95))
            if check['merit_gate_c_relative_p95']>0.01:
                raise ValueError('20x20 MERIT changed validated original Gate C values by >1%')
        atomic_json(BASE/'reports'/'merit_20_online_gate_pass.json',{'key':key,'file_sha256':sha256(path),
              'reference_sha256':sha256(ref),'relative_p95':check['merit_gate_c_relative_p95']})
    z['local_qc_pass']=True;z['qc']=check
    atomic_json(STATIC_LEDGER,rows)
    atomic_json(BASE/'reports'/(key+'.qc.json'),check)
    return check

def merit_merge(out=None):
    import pandas as pd
    import numpy as np
    import rasterio
    c=_root();g=load_gf10(c['gf10'],True)
    rows=load_json(STATIC_LEDGER,[]);passed=[r for r in rows if r.get('local_qc_pass')]
    if not passed:raise ValueError('No approved MERIT tiles')
    frames=[];allids=set()
    for r in passed:
        tif=BASE/'downloads'/r['file']
        if not tif.exists():raise FileNotFoundError(tif)
        with rasterio.open(tif) as ds:
            a=ds.read(masked=True).filled(np.nan)
            ri,ci=np.indices((ds.height,ds.width))
            xx=r['grid_x0']+ci
            yy=r['grid_y0']+ds.height-1-ri
            keys=[f'{int(x)}_{int(y)}' for x,y in zip(xx.ravel(),yy.ravel())]
            if any(k in allids for k in keys):raise ValueError('Two overlapping or duplicate MERIT tiles')
            allids.update(keys)
            frame=pd.DataFrame({'grid_id':keys})
            for i,n in enumerate(M1_FIELDS):frame[n]=a[i].ravel()
            frames.append(frame)
    union=pd.concat(frames,ignore_index=True)
    final=g[['grid_id','grid_x','grid_y','land_area_km2']].merge(union,how='left',on='grid_id',validate='one_to_one')
    if len(final)!=GRID_N:raise ValueError('Frozen GF10 lost in MERIT merge')
    out=Path(out) if out else BASE/'data'/'gf10_merit_partial_v3.parquet'
    out.parent.mkdir(parents=True,exist_ok=True);final.to_parquet(out,index=False)
    audit={'n_gf10':len(final),'n_cells_with_merit':int(final[M1_FIELDS[0]].notna().sum()),
           'n_approved_tiles':len(passed),'all_global_complete':all(k in allids for k in g.grid_id),
           'note':'NoData remains NaN; not a physical flood validation.'}
    atomic_json(out.with_suffix('.qc.json'),audit)
    return audit


def weather_plan(events,block=50):
    import pandas as pd
    c=_root();g=load_gf10(c['gf10'],True)
    path=Path(events)
    if not path.exists():raise FileNotFoundError(path)
    frame=pd.read_parquet(path,columns=['grid_id','date_utc']) if path.suffix.lower()=='.parquet' else pd.read_csv(path,usecols=['grid_id','date_utc'])
    joined,plan=make_event_plan(frame,g,block)
    out=BASE/'plans';out.mkdir(exist_ok=True,parents=True)
    joined.to_parquet(out/'weather_grid_days.parquet',index=False)
    plan.to_csv(out/'weather_tasks.csv',index=False)
    atomic_json(out/'weather_plan.meta.json',{'source_sha':sha256(path),'gf10_sha':c['gf10_sha256'],
       'plan_sha':sha256(out/'weather_tasks.csv'),'n_unique_gf10_dates':len(joined),
       'n_event_task_blocks':len(plan),'n_unique_dates':joined.date_utc.nunique(),
       'warning':'No simulated full-global grid-day table. Date*tile tasks may still be large; approve pilot EECU before bulk.'})
    return load_json(out/'weather_plan.meta.json')

def weather_submit(key=None,execute=False,confirm=None,pilot=False,date='2023-06-01'):
    import pandas as pd
    from ceeprodgee.grid import tile_bounds
    from .weather import TRANSFORM
    if not execute:return {'status':'DRY_RUN','no_ee_tasks_submitted':True}
    if confirm!=RUN_ID:raise ValueError('Exact CEE v3 run id confirmation required')
    c=_root();ee=_ee();rows=_ledger_status(ee,EVENT_LEDGER)
    if any(r['state'] not in ('SUCCEEDED','COMPLETED') or not r.get('local_qc_pass') for r in rows):
        raise RuntimeError('Previous weather task incomplete or unaudited; one at a time')
    if pilot:
        validated_date(date)
        x,y,n=1100,370,10
        key=f'met_{date}_{x}_{y}_{n}'
    else:
        if not key:raise ValueError('Frozen event key required')
        plan=BASE/'plans'/'weather_tasks.csv';meta=load_json(BASE/'plans'/'weather_plan.meta.json')
        if not meta or sha256(plan)!=meta['plan_sha'] or c['gf10_sha256']!=meta['gf10_sha']:
            raise ValueError('Freeze case/control date plan before submitting event tasks')
        matches=pd.read_csv(plan).query('key == @key')
        if len(matches)!=1:raise ValueError('Event group unknown/nonunique')
        row=matches.iloc[0]
        date=str(row.date_utc);x=int(row.bx);y=int(row.by);n=int(row.tile_size)
    if any(r['key']==key for r in rows):raise ValueError('Duplicate meteorology date block')
    weather_budget_h=300.0
    already=0.0
    for r in rows:
        if r.get('eecu_hours') is None:
            raise RuntimeError('Existing weather task EECU unknown; do not charge another task')
        already+=r['eecu_hours']
    if already>=weather_budget_h:raise RuntimeError('300 EECU-h weather budget guard reached')
    roi=ee.Geometry.Rectangle(tile_bounds(x,y,n),proj=_wkt(),geodesic=False)
    # Probe narrow ERA5 and IMERG source date *before* spending batch EECU.
    d=ee.Date(date)
    count_era=ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').filterDate(d.advance(-1,'day'),d).size().getInfo()
    if count_era!=1:raise ValueError('ERA5 D-1 must have exactly one daily image')
    count_day=ee.ImageCollection('NASA/GPM_L3/IMERG_V07').filter(ee.Filter.eq('status','permanent')).filterDate(d,d.advance(1,'day')).size().getInfo()
    if count_day!=48:raise ValueError(f'IMERG V07 permanent D must have 48 records, found {count_day}; no missing-as-zero')
    im=event_image(ee,date,roi,_wkt()).unmask(-9999)
    name=f'{RUN_ID}_{key}'.replace('-','')
    task=ee.batch.Export.image.toDrive(image=im,description=name,folder=c['drive_folder'],
       fileNamePrefix=name,region=roi,crs=_wkt(),crsTransform=TRANSFORM,
       maxPixels=1e7,fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    task.start();state=task.status()
    record={'key':key,'kind':'METEOROLOGY_GF10_DATE','pilot':pilot,'date_utc':date,
      'grid_x0':x,'grid_y0':y,'size':n,'task_id':task.id,
      'operation':state.get('name') or f"projects/{c['project']}/operations/{task.id}",
      'state':state.get('state'),'file':name+'.tif','local_qc_pass':False,
      'project':c['project'],'grid_sha':c['gf10_sha256'],'bands':list(METEO_BANDS)}
    rows.append(record);atomic_json(EVENT_LEDGER,rows)
    return record

def weather_audit(key,file=None):
    c=_root();ee=_ee();rows=_ledger_status(ee,EVENT_LEDGER)
    t=[x for x in rows if x['key']==key]
    if len(t)!=1:raise ValueError('Unknown weather key')
    rec=t[0]
    if rec['state'] not in ('SUCCEEDED','COMPLETED'):raise RuntimeError('Weather EE export not successful')
    p=Path(file) if file else BASE/'downloads'/rec['file']
    report=validate_weather_raster(p,rec['grid_x0'],rec['grid_y0'],rec['size'])
    # Approval is only of source completeness and physical units, not flood validation.
    rec['local_qc_pass']=True;rec['qc']=report
    atomic_json(EVENT_LEDGER,rows)
    atomic_json(BASE/'reports'/(key+'.weatherqc.json'),report)
    return report

def all_status():
    ee=_ee()
    a=_ledger_status(ee,STATIC_LEDGER);b=_ledger_status(ee,EVENT_LEDGER)
    def report(z):
        return {'n_submitted':len(z),
                'n_locally_qc_approved':sum(r.get('local_qc_pass',False) for r in z),
                'eecu_hours_known':round(sum((r.get('eecu_hours') or 0) for r in z),5),
                'n_unknown_eecu':sum(r.get('eecu_hours') is None for r in z),
                'last_tasks':[{'key':r['key'],'state':r['state'],'file':r['file'],
                     'qc_pass':r.get('local_qc_pass',False), 'eecu_hours':r.get('eecu_hours')} for r in z[-4:]]}
    return {'project':_root()['project'], 'merit':report(a), 'weather':report(b)}
