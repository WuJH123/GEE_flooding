"""GF10 GEE v4 sidecar production: no changes to v3 ledger or accepted data."""
from __future__ import annotations
import argparse,json,pathlib,sys,os,re
from . import io,geometry

HOME=pathlib.Path(__file__).resolve().parents[1]
CFG=HOME/'config'/'recovery.json'
LEDGER=HOME/'reports'/'recovery_tasks.json'
PLAN=HOME/'plans'/'merit_safe_v4.csv'
QUAR=HOME/'plans'/'merit_quarantine_v4.csv'

def deps():
    try:
        import ceeprodgee.ee_model as source
        import ceeprodgee.contract as contract
    except ImportError as exc:
        raise RuntimeError('No verified upstream v3 installed. Launch via scripts/00_init.ps1 with PYTHONPATH of v3 package.') from exc
    return source,contract

def conf():
    c=io.load(CFG)
    if not c:raise FileNotFoundError('Run `python -m cee_recover.run init --v3 ...` first')
    if io.sha(c['grid_path'])!=c['grid_sha256']:
        raise ValueError('Frozen GF10 parquet changed since v4 setup')
    if c.get('status')!='CONFIG_LOCKED':raise ValueError('Recovery configuration unapproved')
    return c

def ee_init(c):
    import ee
    ee.Initialize(project=c['project'])
    return ee

def init(a):
    src=pathlib.Path(a.v3).resolve()
    old=src/'config'/'production.json'
    legacy=src/'reports'/'task_ledger.json'
    if not old.exists() or not legacy.exists():raise FileNotFoundError('Existing v3 run and ledger required; do not initialize a new Cloud project')
    oldc=io.load(old)
    if oldc['project']!='future-shuttle-513705-g9':raise ValueError('Wrong CEE Earth Engine project')
    if oldc['run_id']!='CEE_GF10_M0M1M2_EFFICIENT_20261105_V3':raise ValueError('Unexpected source version; audit manually')
    if not oldc.get('pilot_merit_passed'):raise ValueError('Original verified Wuhan MERIT v3 pilot not recorded in config')
    if not pathlib.Path(oldc['grid_path']).exists():raise FileNotFoundError('Frozen GF10 source missing')
    import pandas as pd
    f=pd.read_parquet(oldc['grid_path'],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    if len(f)!=1395471 or f.grid_id.duplicated().any() or abs(f.land_area_km2.sum()-133095959.3496587)>0.05:
        raise ValueError('GF10 count/area mismatch')
    if io.sha(oldc['grid_path'])!=oldc['grid_sha256']:raise ValueError('Frozen GF10 SHA changed')
    saved=io.load(legacy,[])
    key='merit_1097_367_10'
    passed=[r for r in saved if r.get('key')==key and r.get('local_qc_pass') is True]
    if len(passed)!=1:raise ValueError('Wuhan successful v3 pilot missing; cannot reuse its proof')
    for record in saved:
        if record.get('operation') is None:raise ValueError('V3 task missing operation id')
    # Freeze provenance; v3 report remains fully untouched and no failed task
    # is ever relabelled as a successful job.
    snapshots=HOME/'reference'/'v3_snapshots'
    io.frozen_copy(old,snapshots/'production_v3.json')
    io.frozen_copy(legacy,snapshots/'task_ledger_v3.json')
    c={'status':'CONFIG_LOCKED','project':oldc['project'],
       'grid_path':oldc['grid_path'],'grid_sha256':oldc['grid_sha256'],
       'v3_path':str(src),'v3_config_sha256':io.sha(old),
       'v3_ledger_sha256':io.sha(legacy),
       'run_id':'CEE_GF10_GEE_EDGE_RECOVERY_V4_20261105',
       'drive_folder':'CEE_GF10_GEE_EDGE_RECOVERY_V4_20261105',
       'crs_wkt':oldc['output_crs_wkt'],
       'spend_limit_h':float(a.max_eecu),
       'proven_merit_pilot':key,
       'source_ledger_treated_readonly':True,
       'created_utc':io.stamp()}
    if CFG.exists():
        old=io.load(CFG)
        if any(old[k]!=c[k] for k in ['grid_sha256','project','run_id','v3_config_sha256']):
            raise FileExistsError('Conflicting existing v4 config; do not overwrite')
        print('REUSED_V4_CONFIG',CFG);return
    io.atomic(CFG,c)
    print(json.dumps({'status':'V4_PROVENANCE_FROZEN','config':str(CFG),
        'grid_rows':len(f),'project':c['project'],'old_ledger_entries':len(saved),'new_tasks':0},indent=2))

def build_plan(a):
    import pandas as pd
    c=conf()
    g=pd.read_parquet(c['grid_path'],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    p=pd.read_csv(pathlib.Path(c['v3_path'])/'plans'/'merit_all.csv')
    if len(p)!=16874 or p.tile_key.duplicated().any() or set(p.family)!={'merit'}:
        raise ValueError('V3 16,874-task frozen MERIT plan is missing/changed; rerun old v3 plan command first')
    # 16,874 * Pandas masks is expensive; exact bbox from pregrouped GF10
    # using the unmodified frozen 10km index coordinates.
    g['tile_x0']=g.grid_x//10*10;g['tile_y0']=g.grid_y//10*10
    bbox=(g.groupby(['tile_x0','tile_y0'],sort=True)
           .agg(min_x=('grid_x','min'),max_x=('grid_x','max'),
                min_y=('grid_y','min'),max_y=('grid_y','max'),n_land=('grid_id','count'))
           .reset_index())
    p=p.merge(bbox,on=['tile_x0','tile_y0'],how='left',validate='one_to_one')
    if p.n_land.isna().any() or not (p.n_land_cells==p.n_land).all():
        raise ValueError('V3 plan not equivalent to frozen GF10 grouped cell counts')
    vl,vr,vb,vt=geometry.valid_limits()
    p['crop_x0']=p.min_x.astype(int)
    p['crop_y0']=p.min_y.astype(int)
    p['width']=(p.max_x-p.min_x+1).astype(int)
    p['height']=(p.max_y-p.min_y+1).astype(int)
    within=((p.crop_x0*10000>=vl+1)&((p.crop_x0+p.width)*10000<=vr-1)&
            (p.crop_y0*10000>=vb+1)&((p.crop_y0+p.height)*10000<=vt-1))
    # Projection safety needs both valid x/y and no geometry seam. Borderline
    # near +-180 edges is deliberately conservative (full rectangular bounds).
    p['status']=within.map({True:'SAFE_COMPACT',False:'QUARANTINE_SEAM'})
    p['cropped_pixels']=p.width*p.height
    if (p.cropped_pixels>100).any() or p.n_land_cells.sum()!=1395471:
        raise ValueError('Cropped plan work count invalid')
    safe=p.loc[within].copy();unsafe=p.loc[~within].copy()
    cols=['tile_key','family','tile_x0','tile_y0','tile_size','n_land_cells',
          'crop_x0','crop_y0','width','height','cropped_pixels','status']
    for dest,part in [(PLAN,safe),(QUAR,unsafe)]:
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            older=pd.read_csv(dest)
            if not older.equals(part[cols].reset_index(drop=True)):
                raise FileExistsError('Previously frozen plan differs: '+str(dest))
        else:part[cols].to_csv(dest,index=False)
    summary={'status':'PLAN_ONLY_NO_GEE','source_v3_tasks':len(p),'safe_tasks':len(safe),
      'quarantined_tasks':len(unsafe),'safe_land_cells':int(safe.n_land_cells.sum()),
      'quarantined_land_cells':int(unsafe.n_land_cells.sum()),
      'original_parent_pixels':int(len(p)*100),'safe_cropped_pixels':int(safe.cropped_pixels.sum()),
      'plan':str(PLAN),'quarantine':str(QUAR),
      'merit_schema':'16 original v3 source bands, no recalculation from 500m percentiles',
      'note':'No real GEE tasks launched; flagged cells must be resolved separately for GLOBAL completion'}
    io.atomic(HOME/'reports'/'plan_summary.json',summary)
    print(json.dumps(summary,indent=2))

def _check_old_active(ee,c):
    saved=io.load(pathlib.Path(c['v3_path'])/'reports'/'task_ledger.json',[])
    for rec in saved:
        op=ee.data.getOperation(rec['operation'])
        st=(op.get('metadata') or {}).get('state','UNKNOWN')
        if st not in ('SUCCEEDED','COMPLETED','FAILED','CANCELLED'):
            raise ValueError('Prior v3 operation not in terminal state: '+rec['key']+' '+str(st))
    return saved

def _read_op(ee,record):
    if not record.get('operation'):
        raise RuntimeError('SUBMISSION_INTENT has no EE operation: reconcile manually before continuing, never resubmit blindly')
    op=ee.data.getOperation(record['operation'])
    meta=op.get('metadata') or {}
    sec=meta.get('batchEecuUsageSeconds',meta.get('batch_eecu_usage_seconds'))
    return {'state':meta.get('state','UNKNOWN'),'eecu_h':float(sec)/3600 if sec is not None else None,
            'error':(op.get('error') or {}).get('message')}

def _all_prior_qc(ee,entries):
    for e in entries:
        st=_read_op(ee,e)
        if st['state'] not in ('SUCCEEDED','COMPLETED'):raise RuntimeError('Unresolved recovery task: '+e['key']+' '+str(st))
        if e.get('local_qc_pass') is not True:
            raise RuntimeError('Recovery task completed but local downloaded GeoTIFF QA not approved: '+e['key'])
        if st['eecu_h'] is None:raise RuntimeError('Missing operation EECU; refuse additional submission')

def _selection(args,c):
    import pandas as pd
    if not PLAN.exists():raise FileNotFoundError('Run plan first')
    p=pd.read_csv(PLAN)
    entries=io.load(LEDGER,[])
    chosen=args.key
    if chosen=='auto':
        taken={x['key'] for x in entries}
        options=p.loc[~p.tile_key.isin(taken)]
        if options.empty:raise ValueError('All safe tasks submitted; boundary quarantine not resolved')
        # Prefer a cheap existing blocked candidate for recovery rather than
        # hide it. The failed V3 first block becomes small cropped 2xN.
        old_first=options.loc[options.tile_key=='merit_-1740_-240_10']
        if not old_first.empty:options=old_first
        row=options.iloc[0]
    else:
        part=p.loc[p.tile_key==chosen]
        if len(part)!=1:
            if QUAR.exists() and chosen in set(pd.read_csv(QUAR).tile_key):
                raise RuntimeError('QUARANTINE_SEAM: cannot submit risky projected rectangle')
            raise KeyError('Not in safe plan: '+str(chosen))
        row=part.iloc[0]
    if row.tile_key in {x['key'] for x in entries}:raise ValueError('Already submitted in v4; no duplicate EECU')
    return row

def preview(a):
    c=conf();r=_selection(a,c)
    crop=geometry.Crop(r.tile_key,int(r.tile_x0),int(r.tile_y0),10,
        int(r.crop_x0),int(r.crop_y0),int(r.width),int(r.height),int(r.n_land_cells),str(r.status),'')
    if crop.status!='SAFE_COMPACT':raise ValueError('Projected region quarantined')
    out={'status':'DRY_RUN_NO_GEE','key':crop.original_key,
         'source_land_cells':crop.n_land,'export_width':crop.width,'export_height':crop.height,
         'raster_pixels':crop.width*crop.height,'full_bounds_m':crop.work_bounds(),
         'pixel_center_envelope_m':crop.export_bounds(),'global_crs_transform':[10000,0,0,0,-10000,0],
         'note':'Valid region geometry, clipped parent bbox, export no more than 100 pixels'}
    print(json.dumps(out,indent=2));return crop

def submit(a):
    c=conf();crop=preview(a)
    if not a.execute:return
    if a.confirm!=c['run_id']:raise ValueError('Incorrect immutable V4 confirmation token')
    if a.key=='auto' and not a.allow_auto:raise ValueError('For production use explicit --key; --allow-auto must be explicitly passed')
    ee=ee_init(c)
    prior=_check_old_active(ee,c)
    registry=io.load(LEDGER,[])
    _all_prior_qc(ee,registry)
    if not c['proven_merit_pilot']:raise ValueError('No independent Gate-C proof in sealed v3')
    spent_v3=[]
    for r in prior:
        z=_read_op(ee,r)
        if z['eecu_h'] is None:raise ValueError('Unreported v3 EECU; refuse additional')
        spent_v3.append(z['eecu_h'])
    spent_v4=sum(_read_op(ee,r)['eecu_h'] for r in registry)
    spent=sum(spent_v3)+spent_v4
    if spent>=c['spend_limit_h'] or spent+0.1>c['spend_limit_h']:
        raise RuntimeError('EECU hard stop; new compute budget reserve exhausted')
    if crop.width*crop.height>100:raise ValueError('Unsafe overlong parent export')
    em,contract=deps()
    roi=ee.Geometry.Rectangle(crop.work_bounds(),proj=c['crs_wkt'],geodesic=False)
    # EE raster export uses a center-inclusive projected region, NOT full
    # rectangle corners, to avoid extra border pixels / wrapping envelope.
    export_roi=ee.Geometry.Rectangle(crop.export_bounds(),proj=c['crs_wkt'],geodesic=False)
    img=em.merit(ee,roi,c['crs_wkt']).unmask(-9999)
    filename=f'{c["run_id"]}_{crop.original_key}'
    kwargs=dict(image=img,description=filename,folder=c['drive_folder'],
        fileNamePrefix=filename,region=export_roi,crs=c['crs_wkt'],
        crsTransform=em.TRANSFORM_10,maxPixels=200,fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized':True,'noData':-9999})
    task=ee.batch.Export.image.toDrive(**kwargs)
    # PRE-REGISTER task intent before touching the remote EE batch scheduler.
    # This prevents accidental duplicate exports if Windows/Python dies after
    # task.start() and before returning its operation ID. Such a record must
    # be manually reconciled; the pipeline intentionally stops on missing IDs.
    record={'key':crop.original_key,'family':'merit','source_v3_failed_key':crop.original_key,
            'project':c['project'],'run_id':c['run_id'],'geometry':crop.as_record(),
            'file':filename+'.tif','bands':list(contract.MERIT_BANDS),
            'operation':None,'task_id':task.id,'submitted_utc':io.stamp(),
            'local_qc_pass':False,'status':'SUBMISSION_INTENT',
            'cost_ceiling_checked_h':c['spend_limit_h'],
            'image_center_region':crop.export_bounds(),'output_affine':[10000,0,0,0,-10000,0],
            'input_grid_sha256':c['grid_sha256']}
    registry.append(record);io.atomic(LEDGER,registry)
    task.start();state=task.status()
    record['operation']=state.get('name') or f'projects/{c["project"]}/operations/{task.id}'
    record['task_id']=task.id
    record['status']=state.get('state')
    io.atomic(LEDGER,registry)
    print('ONE_SAFE_BOUNDED_MERIT_EXPORT_SUBMITTED; DOWNLOAD TIFF AND AUDIT BEFORE NEXT SUBMISSION')
    print(json.dumps(record,indent=2))

def status(a):
    c=conf();records=io.load(LEDGER,[])
    if not records:print('NO_RECOVERY_JOBS');return
    ee=ee_init(c);total=0;unknown=False
    for z in records:
        state=_read_op(ee,z);z['state']=state['state'];z['eecu_h']=state['eecu_h'];z['error']=state['error']
        if state['eecu_h'] is None:unknown=True
        else:total+=state['eecu_h']
    io.atomic(LEDGER,records)
    print(json.dumps({'jobs':[{k:z.get(k) for k in ('key','state','eecu_h','error','local_qc_pass')} for z in records],
          'known_recovery_eecu_h':total,'some_costs_not_reported':unknown},indent=2))

def audit(a):
    import rasterio
    c=conf();registry=io.load(LEDGER,[])
    matches=[z for z in registry if z['key']==a.key]
    if len(matches)!=1:raise ValueError('Unknown v4 task key')
    rec=matches[0]
    state=_read_op(ee_init(c),rec)
    if state['state'] not in ('SUCCEEDED','COMPLETED'):raise ValueError('GEE task not successful')
    crop=geometry.Crop(**rec['geometry'])
    path=pathlib.Path(a.file or HOME/'downloads'/rec['file'])
    if not path.is_file():raise FileNotFoundError(path)
    with rasterio.open(path) as ds:
        t=ds.transform
        profile={'crs':ds.crs.to_epsg(),'width':ds.width,'height':ds.height,
                 'count':ds.count,'transform':[t.a,t.b,t.c,t.d,t.e,t.f]}
    geometry.validate_raster_metadata(profile,crop)
    _,contract=deps()
    from ceeprodgee import qc
    outcome=qc.check_raster(path,'merit',expected_manifest=tuple(contract.MERIT_BANDS))
    rec['local_qc_pass']=True;rec['verified_sha256']=io.sha(path)
    rec['eecu_h']=state['eecu_h'];rec['qc']=outcome
    io.atomic(LEDGER,registry)
    io.atomic(HOME/'reports'/(a.key+'.qc.json'),{'status':'ACCEPTED_V4_COMPACT_GEOMETRY',
           'raster_sha256':rec['verified_sha256'],'source_v3_history_untouched':True,
           'crop':rec['geometry'],'qc':outcome})
    print('ACCEPTED',a.key,crop.width,crop.height,'actual grid cells',crop.n_land)

def merge(a):
    import pandas as pd,numpy as np,rasterio
    c=conf()
    g=pd.read_parquet(c['grid_path'],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    records=[z for z in io.load(LEDGER,[]) if z.get('local_qc_pass')]
    if not records:raise RuntimeError('No QA-passed v4 records')
    _,contract=deps()
    columns=list(contract.MERIT_BANDS)
    seen={};extra=[]
    for rec in records:
        p=HOME/'downloads'/rec['file']
        if not p.exists():raise FileNotFoundError(p)
        if io.sha(p)!=rec['verified_sha256']:raise ValueError('QA-accepted file hash changed')
        crop=geometry.Crop(**rec['geometry'])
        with rasterio.open(p) as ds:
            xx=np.tile(np.arange(crop.x_min,crop.x_min+crop.width),crop.height)
            yy=np.repeat(np.arange(crop.y_min+crop.height-1,crop.y_min-1,-1),crop.width)
            vals=ds.read(masked=True).filled(np.nan)
        keys=[f'{x}_{y}' for x,y in zip(xx,yy)]
        if any(k in seen for k in keys):raise ValueError('Overlapping v4 output keys')
        for k in keys:seen[k]=True
        part=pd.DataFrame({'grid_id':keys})
        for band,name in enumerate(columns):part[name]=vals[band].ravel()
        extra.append(part)
    all_data=pd.concat(extra,ignore_index=True)
    joined=g.merge(all_data,on='grid_id',how='left',validate='one_to_one')
    if len(joined)!=1395471:raise ValueError('Global reference count lost')
    output=HOME/'data'/'merit_v4_recovery_partial.parquet'
    if output.exists():raise FileExistsError('Immutable merge already generated')
    output.parent.mkdir(parents=True,exist_ok=True)
    joined.to_parquet(output,index=False)
    result={'status':'PARTIAL_NOT_GLOBAL_COMPLETE','n_GF10':len(joined),
            'n_export_pixels':len(all_data),'n_nonmissing_merit':int(joined[columns[0]].notna().sum()),
            'n_seam_quarantined':int(pd.read_csv(QUAR).n_land_cells.sum()),
            'source_schema':columns,'note':'The v4 partial cannot be called global without accepted boundary recovery and all safe tiles'}
    io.atomic(output.with_suffix('.qc.json'),result)
    print(json.dumps(result,indent=2))

def main():
    p=argparse.ArgumentParser(description='CEE GF10 v4 edge recovery; preserve v3 scientific calculations')
    sub=p.add_subparsers(dest='cmd',required=True)
    z=sub.add_parser('init');z.add_argument('--v3',required=True);z.add_argument('--max-eecu',type=float,default=300)
    sub.add_parser('plan')
    z=sub.add_parser('preview');z.add_argument('--key',default='auto')
    z=sub.add_parser('submit');z.add_argument('--key',required=True);z.add_argument('--execute',action='store_true');z.add_argument('--confirm');z.add_argument('--allow-auto',action='store_true')
    sub.add_parser('status')
    z=sub.add_parser('audit');z.add_argument('--key',required=True);z.add_argument('--file')
    sub.add_parser('merge')
    a=p.parse_args()
    {'init':init,'plan':build_plan,'preview':preview,'submit':submit,'status':status,'audit':audit,'merge':merge}[a.cmd](a)
if __name__=='__main__':main()
