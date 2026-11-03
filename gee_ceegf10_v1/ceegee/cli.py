"""No automatic global EE submission. All exports isolated by Cloud project + run ID.

Functions calculate task EECU from official OperationMetadata. Batch cost is
not predictable from wall-clock time and must be measured first.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, re, sys
from . import grid, models

HOME = pathlib.Path(__file__).resolve().parents[1]
CONFIG = HOME/'config'/'local_run.json'
ROOT_PREFIX = 'CEE_GF10_CEE_V1_'
BUDGET_EECU_HOURS = 1000.0


def save_json(path, val):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.writing')
    tmp.write_text(json.dumps(val,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def read_cfg():
    if not CONFIG.is_file():raise SystemExit('Run setup first. A dedicated EE Cloud project ID is required.')
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def get_ee(config):
    import ee
    ee.Initialize(project=config['project'])
    return ee


def operation_status(ee, name):
    if not name:return {'state':'UNKNOWN','eecu_hours':None}
    try:
        o=ee.data.getOperation(name)
        md=o.get('metadata',{})
        seconds=md.get('batchEecuUsageSeconds',md.get('batch_eecu_usage_seconds'))
        return {'state':md.get('state','UNKNOWN'), 'eecu_hours':float(seconds)/3600 if seconds is not None else None,
                'operation':name,'error':o.get('error',{}).get('message')}
    except Exception as exc:
        return {'state':'QUERY_ERROR','error':str(exc),'operation':name}


def submit_task(ee,config,task,label,record):
    registry_path=HOME/'reports'/'tasks.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else []
    if any(item['label']==label for item in registry):
        raise ValueError(f'Task label already submitted: {label}. Refuse duplicate even after restart.')
    task.start()  # Explicit user submission is the only path starting EECU jobs.
    status=task.status()
    registry.append({'label':label,'task_id':task.id,'operation':status.get('name'),
                     'state_submitted':status.get('state'),'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                     'project':config['project'], **record})
    save_json(registry_path,registry)
    print(json.dumps(registry[-1],ensure_ascii=False,indent=2))


def make_sample(ee,g,limit=16):
    s=grid.select_pilot(g,limit)
    sample=grid.pilot_features(ee,s)
    return s,sample


def create_root(ee,asset_folder):
    try:
        ee.data.getAsset(asset_folder)
    except Exception as e:
        message=str(e).lower()
        if not any(w in message for w in ('not found','404','does not exist')):
            raise
    else:
        raise FileExistsError('GEE isolation prefix already exists; new run_id required: '+asset_folder)
    ee.data.createAsset({'type':'FOLDER'},asset_folder)
    return asset_folder


def setup(args):
    if CONFIG.exists():raise SystemExit('Existing project config found; refusing to overwrite and possibly touch a different project')
    project=args.project
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]',project):
        raise ValueError('Invalid Cloud project ID syntax')
    g=grid.load_grid(args.grid)
    run_id=args.run_id or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')
    if not re.fullmatch('[0-9A-Za-z_]{8,40}',run_id):raise ValueError('Invalid run id')
    c={'project':project,'grid':str(pathlib.Path(args.grid).resolve()),'run_id':run_id,
       'asset_root':f'projects/{project}/assets/{ROOT_PREFIX}{run_id}',
       'drive_folder':f'{ROOT_PREFIX}{run_id}', 'budget_hours':BUDGET_EECU_HOURS,
       'min_free_budget_fraction':0.4,'pilot_approved':False,
       'grid_spec':grid.limits(g),'output_crs':'EPSG:6933','output_transform':[10000,0,0,0,-10000,0]}
    save_json(CONFIG,c)
    print('CONFIG_SAVED_NO_EE_TASKS_STARTED:',CONFIG)
    print('Project isolation:',c['asset_root'])


def init(args):
    c=read_cfg()
    ee=get_ee(c)
    create_root(ee,c['asset_root'])
    print('NEW_ISOLATED_EE_ASSET_FOLDER_CREATED:',c['asset_root'])
    print('No other project assets read, imported, edited or removed.')


def source_probe(args):
    c=read_cfg();ee=get_ee(c)
    results={}
    for key,source in {'merit':'MERIT/Hydro/v1_0_1','worldcover':'ESA/WorldCover/v200',
                       'imerg':'NASA/GPM_L3/IMERG_V07','era5land':'ECMWF/ERA5_LAND/DAILY_AGGR'}.items():
        img=ee.Image(source) if key=='merit' else ee.ImageCollection(source).first()
        results[key]={'id':source,'bands':img.bandNames().getInfo()}
    assert {'hnd','upa','elv','wat'}.issubset(set(results['merit']['bands']))
    assert 'Map' in results['worldcover']['bands']
    assert 'precipitation' in results['imerg']['bands']
    for name in ('volumetric_soil_water_layer_1','temperature_2m','total_precipitation_sum'):
        assert name in results['era5land']['bands'],name
    save_json(HOME/'reports'/'sources.json',results)
    print(json.dumps(results,ensure_ascii=False,indent=2))


def _sample_reduce(ee,img,fc,scale):
    # Local polygon keys are preserved without importing a 1.4M feature asset.
    return img.reduceRegions(collection=fc,reducer=ee.Reducer.mean(),
                             crs='EPSG:6933',scale=scale,tileScale=4)


def pilot_static(args):
    c=read_cfg();ee=get_ee(c)
    g=grid.load_grid(c['grid']);s,fc=make_sample(ee,g,args.cells)
    save_json(HOME/'reports'/'pilot_cells.json',s.to_dict('records'))
    count=0
    for family in args.families:
        native=models.static_native(ee,family)
        approx=models.static_image(ee,family)
        scale=10 if family=='worldcover' else 90
        for label,imag,use_scale in [('reference',native,scale),('production',approx,10000)]:
            tag=f'{family}_{label}_{len(s)}'
            asset=f"{c['asset_root']}/pilot_{tag}"
            task=ee.batch.Export.table.toAsset(collection=_sample_reduce(ee,imag,fc,use_scale),
                    description=f"{ROOT_PREFIX}{c['run_id']}_{tag}",assetId=asset)
            submit_task(ee,c,task,tag,{'family':family,'kind':'PILOT_TABLE','asset':asset,
                              'n_cells':len(s),'source_scale_m':use_scale})
            count+=1
    print('PILOT_TASKS_SUBMITTED',count,'- NOT global exports')


def collect_task_costs(args):
    c=read_cfg();ee=get_ee(c)
    path=HOME/'reports'/'tasks.json'
    if not path.exists():raise FileNotFoundError('No tasks have been submitted')
    records=json.loads(path.read_text(encoding='utf-8'))
    for item in records:
        status=operation_status(ee,item.get('operation'))
        if status['state']=='UNKNOWN' and item.get('task_id'):
            try:
                st=ee.data.getTaskStatus(item['task_id'])[0]
                secs=st.get('batch_eecu_usage_seconds')
                status={'state':st.get('state','UNKNOWN'),
                        'eecu_hours':float(secs)/3600 if secs is not None else None}
            except Exception:pass
        item.update(current=status)
    save_json(path,records)
    print(json.dumps([{k:v for k,v in item.items() if k in ('label','current')} for item in records],indent=2))


def qa_pilot(args):
    import numpy as np
    import pandas as pd
    c=read_cfg();ee=get_ee(c)
    registry=json.loads((HOME/'reports'/'tasks.json').read_text(encoding='utf-8'))
    report={'status':'PILOT_FAILED','checks':{},'project':c['project'],'asset_root':c['asset_root']}
    ok=True
    n=int(json.loads((HOME/'reports'/'pilot_cells.json').read_text(encoding='utf-8')).__len__())
    for family in args.families:
        rec={}
        for label in ('reference','production'):
            taskname=f'{family}_{label}_{n}'
            item=next((x for x in registry if x['label']==taskname),None)
            if not item:raise FileNotFoundError('Missing submitted pilot task: '+taskname)
            op=operation_status(ee,item.get('operation'))
            if op['state'] not in ('SUCCEEDED','COMPLETED'):
                raise RuntimeError(f'{taskname} not yet succeeded or operation unavailable: {op}')
            vals=ee.FeatureCollection(item['asset']).getInfo()['features']
            if len(vals)!=n:raise ValueError(f'{taskname}: expected {n} result records, got {len(vals)}')
            rows={str(x['properties']['grid_id']):x['properties'] for x in vals}
            if len(rows)!=n:raise ValueError('Duplicate GF10 ID in GEE pilot')
            rec[label]=rows
            item.setdefault('current',{}).update(op)
        compare=[]
        for cell,one in rec['reference'].items():
            two=rec['production'].get(cell)
            if two is None:raise ValueError('Missing pilot cell in coarse output: '+cell)
            for col,val in one.items():
                if col in ('grid_id','land_area_km2','pilot_type','system:index') or not isinstance(val,(int,float)):
                    continue
                other=two.get(col)
                if val is None or other is None or not np.isfinite(val) or not np.isfinite(other):
                    continue
                if family=='worldcover':
                    compare.append(abs(val-other)) # absolute fraction difference
                else:
                    # relative deviation per hydrologic background; exact metric varies by terrain.
                    if abs(val)>1:compare.append(abs(val-other)/max(1,abs(val)))
            if family=='worldcover':
                fractions=[v for k,v in one.items() if k.startswith('wc_') and k.endswith('_fraction_fullcell') and k!='wc_valid_fraction_fullcell']
                valid=one.get('wc_valid_fraction_fullcell')
                if valid is not None and fractions and abs(sum(v or 0 for v in fractions)-valid)>0.025:
                    raise ValueError(f'WorldCover class area conservation failed for {cell}')
        p50=float(np.median(compare)) if compare else None
        p95=float(np.percentile(compare,95)) if compare else None
        threshold=.05 if family=='worldcover' else .35
        passed=p95 is not None and p95<=threshold
        ok=ok and passed
        report['checks'][family]={'sample_cells':n,'compared_values':len(compare),'median_error':p50,
            'p95_error':p95,'threshold':threshold,'pass':passed,
            'not_land_clipped':True,'caveat':'Pilot compares 10m/90m source against GF10 output, not independent ground truth'}
    report['status']='PILOT_TECHNICAL_QA_PASS_NEEDS_MANUAL_REVIEW' if ok else 'PILOT_QA_FAILED_NO_FULL_APPROVAL'
    save_json(HOME/'reports'/'pilot_qa.json',report)
    print(json.dumps(report,indent=2))
    if not ok:raise SystemExit('Pilot mismatch exceeds tolerance; do not submit global production')


def approve(args):
    c=read_cfg()
    qa=json.loads((HOME/'reports'/'pilot_qa.json').read_text(encoding='utf-8'))
    if qa['status']!='PILOT_TECHNICAL_QA_PASS_NEEDS_MANUAL_REVIEW':
        raise RuntimeError('Pilot QA did not pass')
    if args.confirm != c['run_id']:
        raise ValueError('Explicit run_id confirmation required to approve full tasks')
    registry=json.loads((HOME/'reports'/'tasks.json').read_text(encoding='utf-8'))
    pilots=[x for x in registry if x['kind']=='PILOT_TABLE']
    if len(pilots)<4:raise RuntimeError('Need all four static pilot exports')
    ee=get_ee(c)
    cost=0.0
    for item in pilots:
        st=operation_status(ee,item.get('operation'))
        if st['state'] not in ('SUCCEEDED','COMPLETED') or st['eecu_hours'] is None:
            raise RuntimeError('Actual EECU-hour usage unavailable for '+item['label']+'; do not approve blindly')
        cost+=st['eecu_hours']
    if cost>3.0:
        raise RuntimeError(f'Pilot consumed {cost:.3f} EECU-hours, investigate before full submission')
    c['pilot_eecu_hours']=cost
    c['pilot_approved']=True
    save_json(CONFIG,c)
    print('FULL_STATIC_SUBMISSION_GATE_APPROVED_WITH_RUN_ID:',c['run_id'])


def projected_strip(ee,c,i,count):
    # Bounds are in units of frozen 10km grid, origin 0, no regridding.
    lo=c['grid_spec'];height=lo['maxy']-lo['miny']
    bottom=lo['miny']+height*i//count
    top=lo['miny']+height*(i+1)//count
    return ee.Geometry.Rectangle([lo['minx']*10000,bottom*10000,
                                   lo['maxx']*10000,top*10000],ee.Projection('EPSG:6933'),False)


def static_full(args):
    c=read_cfg()
    if not c.get('pilot_approved'):raise RuntimeError('PILOT_QA gate not approved; never submit full jobs first')
    if args.count<=0 or args.count>2:
        raise ValueError('Only 1-2 full-region strips per submission allowed; measure EECU after each batch')
    if args.strip<0 or args.strip+args.count>args.strips:raise ValueError('strip range out of bounds')
    if args.family not in models.STATIC_FAMILIES:raise ValueError('Unknown static family')
    ee=get_ee(c)
    # Gate every subsequent strip on a COMPLETED prior-strip benchmark and local
    # validation of a downloaded GeoTIFF. Never submit 12 global stripes blindly.
    if args.strip>0:
        regfile=HOME/'reports'/'tasks.json'
        registry=json.loads(regfile.read_text(encoding='utf-8'))
        prior=[x for x in registry if x.get('kind')=='FULL_STATIC_STRIP' and x['family']==args.family]
        if not prior:raise RuntimeError('First full-region stripe must finish before subsequent stripes')
        qcfile=HOME/'reports'/f'local_tif_verified_{args.family}.json'
        if not qcfile.exists():raise RuntimeError(f'Download first {args.family} stripe, validate-tif with --family, before proceeding')
        spent=[]
        for p in prior:
            st=operation_status(ee,p.get('operation'))
            if st['state'] not in ('SUCCEEDED','COMPLETED') or st['eecu_hours'] is None:
                raise RuntimeError('Prior full stripe not finished or EECU unavailable: '+p['label'])
            spent.append(st['eecu_hours'])
        estimate=sum(spent)/len(spent)*args.strips*2.0 # 2x contingency, NOT a guarantee
        if estimate>250:
            raise RuntimeError(f'{args.family} estimated {estimate:.1f} EECU-hours > 250h static family gate; pause and redesign')
        print('CONSERVATIVE_FULL_FAMILY_ESTIMATE_EECU_HOURS',round(estimate,3))
    ee=get_ee(c)
    image=models.static_image(ee,args.family)
    for i in range(args.strip,args.strip+args.count):
        label=f'full_{args.family}_strip_{i:02d}_of_{args.strips:02d}'
        region=projected_strip(ee,c,i,args.strips)
        task=ee.batch.Export.image.toDrive(
            image=image,description=f'{ROOT_PREFIX}{c["run_id"]}_{label}',
            folder=c['drive_folder'],fileNamePrefix=label,
            region=region,crs=c['output_crs'],crsTransform=c['output_transform'],
            maxPixels=2e8,fileFormat='GeoTIFF',
            formatOptions={'cloudOptimized':True,'noData':-9999})
        submit_task(ee,c,task,label,{'kind':'FULL_STATIC_STRIP',
                     'family':args.family,'strip':i,'total_strips':args.strips,
                     'output':'Google Drive/'+c['drive_folder'],'not_land_clipped':True})
    print('Submitted',args.count,'strips only. Read EECU consumption and local raster QC before more submissions.')


def event_pilot(args):
    c=read_cfg();ee=get_ee(c)
    g=grid.load_grid(c['grid'])
    s,fc=make_sample(ee,g,args.cells)
    # This date is METHOD VALIDATION ONLY, not a verified flooded episode.
    im=models.climate_for_event_date(ee,args.date)
    sample=im.reduceRegions(collection=fc,reducer=ee.Reducer.mean(),
            crs='EPSG:6933',scale=10000,tileScale=4)
    label='event_pilot_'+args.date.replace('-','')
    aid=f"{c['asset_root']}/{label}"
    task=ee.batch.Export.table.toAsset(collection=sample,
                description=f'{ROOT_PREFIX}{c["run_id"]}_{label}',assetId=aid)
    submit_task(ee,c,task,label,{'kind':'EVENT_METHOD_PILOT','date_utc':args.date,
                     'asset':aid,'warning':'NOT a historical flood case; method validation only'})


def local_tif_qa(args):
    import rasterio
    import numpy as np
    p=pathlib.Path(args.file)
    with rasterio.open(p) as ds:
        if ds.crs is None or ds.crs.to_epsg()!=6933:
            raise ValueError('Downloaded raster is not EPSG:6933')
        vals=ds.transform
        if abs(vals.a-10000)>0.01 or abs(vals.e+10000)>0.01 or abs(vals.b)>1e-6 or abs(vals.d)>1e-6:
            raise ValueError('GeoTIFF not at frozen 10km cell size')
        if abs(vals.c/10000-round(vals.c/10000))>1e-6 or abs(vals.f/10000-round(vals.f/10000))>1e-6:
            raise ValueError('GeoTIFF origin is not GF10 anchored to zero')
        if ds.count<4:raise ValueError('Insufficient expected output bands')
        sample=ds.read(window=rasterio.windows.Window(0,0,min(100,ds.width),min(100,ds.height)),masked=True)
        result={'file':str(p),'shape':[ds.height,ds.width,ds.count],
             'transform':tuple(ds.transform),'crs':str(ds.crs),'sample_n_valid':int(np.sum(~sample.mask))}
    print(json.dumps(result,indent=2))
    if args.family:
        save_json(HOME/'reports'/f'local_tif_verified_{args.family}.json',result)


def guard_budget(args):
    """Only user-created tasks in THIS run; does not touch other GEE projects."""
    c=read_cfg();ee=get_ee(c)
    registry_file=HOME/'reports'/'tasks.json'
    if not registry_file.exists():raise RuntimeError('No tasks registered under this CEE run')
    tasks=json.loads(registry_file.read_text(encoding='utf-8'))
    total=0.0;cancelled=[];unknown=[]
    for item in tasks:
        if item.get('project') != c['project'] or not item.get('label'):
            raise ValueError('Unexpected project/label in isolated registry')
        st=operation_status(ee,item.get('operation'))
        if st['eecu_hours'] is None:
            unknown.append(item['label'])
            continue
        total+=st['eecu_hours']
        if st['state']=='RUNNING' and st['eecu_hours']>args.max_task_hours:
            if args.cancel and item.get('operation'):
                ee.data.cancelOperation(item['operation'])
                cancelled.append(item['label'])
            else: print('WARNING TASK OVER LIMIT:',item['label'],st['eecu_hours'])
    print(json.dumps({'total_eecu_hours_this_run':round(total,3),'nonreported':unknown,
             'cancelled_by_request':cancelled,'max_per_task_hours':args.max_task_hours},indent=2))
    if total>args.max_run_hours:
        raise SystemExit('BUDGET_LIMIT_REACHED: stop submitting new tasks; check Cloud quotas and monitoring')


def merge_static(args):
    from .merge import join_exports
    c=read_cfg()
    tif_dir=pathlib.Path(args.tif_dir) if args.tif_dir else HOME/'data'/'downloads'/args.family
    out=HOME/'data'/'derived'/f'GF10_GEE_{args.family}_20261103.parquet'
    print(json.dumps(join_exports(c['grid'],tif_dir,args.family,out,args.strips),ensure_ascii=False,indent=2))


def main(argv=None):
    ap=argparse.ArgumentParser(description='CEE-GF10 v1 isolated pilot-gated Earth Engine production')
    s=ap.add_subparsers(dest='cmd',required=True)
    p=s.add_parser('setup');p.add_argument('--project',required=True);p.add_argument('--grid',required=True);p.add_argument('--run-id')
    s.add_parser('init');s.add_parser('source-probe')
    for action in ('pilot-static','qa-pilot'):
        p=s.add_parser(action);p.add_argument('--families', nargs='+',choices=models.STATIC_FAMILIES,default=list(models.STATIC_FAMILIES))
        if action=='pilot-static':p.add_argument('--cells',type=int,default=16)
    s.add_parser('tasks')
    p=s.add_parser('approve');p.add_argument('--confirm',required=True)
    p=s.add_parser('submit-static');p.add_argument('--family',choices=models.STATIC_FAMILIES,required=True)
    p.add_argument('--strip',type=int,default=0);p.add_argument('--count',type=int,default=1);p.add_argument('--strips',type=int,default=12)
    p=s.add_parser('pilot-event');p.add_argument('--date',default='2023-06-01');p.add_argument('--cells',type=int,default=12)
    p=s.add_parser('validate-tif');p.add_argument('--file',required=True);p.add_argument('--family',choices=models.STATIC_FAMILIES)
    p=s.add_parser('guard-budget');p.add_argument('--max-task-hours',type=float,default=25.0);p.add_argument('--max-run-hours',type=float,default=300.0);p.add_argument('--cancel',action='store_true')
    p=s.add_parser('merge-static');p.add_argument('--family',choices=models.STATIC_FAMILIES,required=True);p.add_argument('--tif-dir');p.add_argument('--strips',type=int,default=12)
    a=ap.parse_args(argv)
    return {'setup':setup,'init':init,'source-probe':source_probe,'pilot-static':pilot_static,
            'tasks':collect_task_costs,'qa-pilot':qa_pilot,'approve':approve,
            'submit-static':static_full,'pilot-event':event_pilot,
            'validate-tif':local_tif_qa,'guard-budget':guard_budget,'merge-static':merge_static}[a.cmd](a)

if __name__=='__main__':main()
