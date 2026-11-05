"""Explicit safe EE MERIT production with frozen GF10, v3 read-only provenance.

No global submission or background loop. One audited tile at a time. Never
relabel a failed v3 raster as valid or erase v3 historical task ledger.
"""
from __future__ import annotations
import argparse,pathlib,json,datetime as dt
from . import core,audit,cohort
ROOT=pathlib.Path(__file__).resolve().parents[1]
REG=ROOT/'reports'/'boundary_v4_ledger.json'
SETTINGS=ROOT/'reports'/'boundary_v4_settings.json'


def v3():
    from ceeprodgee import grid,ee_model,contract,qc
    base=pathlib.Path(__import__('ceeprodgee').__file__).resolve().parents[1]
    config=core.load(base/'config'/'production.json')
    if not config:raise FileNotFoundError('Run v3 configure and verify first; v4 never guesses project/grid')
    if config.get('run_id')!='CEE_GF10_M0M1M2_EFFICIENT_20261105_V3':raise ValueError('Unexpected v3 project/run ID')
    return base,config,grid,ee_model,contract


def frozen():
    base,c,gmod,model,ct=v3()
    if core.hash_file(c['grid_path'])!=c['grid_sha256']:raise ValueError('GF10 sha256 mismatch')
    g=gmod.read_grid(c['grid_path'],strict=True)
    return base,c,g,model,ct


def _ee(conf):
    import ee
    ee.Initialize(project=conf['project']);return ee


def state(ee,rec):
    from ceeprodgee import ledger
    return ledger.task_state(ee,rec['operation'])


def inspect(args):
    import pandas as pd
    base,c,g,model,ct=frozen()
    plan=pathlib.Path(args.plan) if args.plan else base/'plans'/'merit_all.csv'
    if not plan.is_file():raise FileNotFoundError('Generate v3 MERIT all-global plan before v4: '+str(plan))
    p=pd.read_csv(plan)
    if p.tile_key.duplicated().any() or not p.tile_size.eq(10).all() or not p.family.eq('merit').all():raise ValueError('Unexpected plan schema')
    p['mode']=[core.projected_mode(core.Tile(int(r.tile_x0),int(r.tile_y0))) for r in p.itertuples()]
    p['need_table']=p['mode'].eq('POINT_TABLE')
    p['n_land_cells_expected']=p.n_land_cells
    out=ROOT/'reports'/'projection_plan_v4.csv';out.parent.mkdir(exist_ok=True,parents=True)
    p.to_csv(out,index=False)
    small=p[p.need_table]
    rep={'status':'PLAN_ONLY_NO_GEE','n_tiles':len(p),'n_edge_table_tiles':len(small),
         'n_regular_tiles':len(p)-len(small),'n_frozen_gf10':len(g),
         'first_edge_tiles':small.tile_key.head(8).tolist(),
         'first_tile':str(p.iloc[0].tile_key),'plan_path':str(out),
         'projection_x_bound_m':core.X_LIMIT,'projection_y_bound_m':core.Y_LIMIT}
    core.atomic_json(ROOT/'reports'/'projection_plan_v4.json',rep);print(json.dumps(rep,indent=2))


def quarantine(args):
    base,c,g,model,ct=frozen()
    older=core.load(base/'reports'/'task_ledger.json',[])
    hit=[x for x in older if x.get('key')==args.key]
    if len(hit)!=1:raise ValueError('Invalid old v3 failed key')
    old=hit[0]
    if old.get('local_qc_pass') or old.get('state') not in ('SUCCEEDED','COMPLETED') or old.get('family')!='merit':raise ValueError('Only succeeded but QC-rejected v3 MERIT may be quarantined')
    if args.key!='merit_-1740_-240_10':raise ValueError('Only independently documented edge failure supported; do not infer other failures')
    r={'old_key':args.key,'v3_original_ledger_sha256':core.hash_file(base/'reports'/'task_ledger.json'),
       'old_task_id':old.get('task_id'),'old_operation':old.get('operation'),
       'old_eecu_hours':old.get('eecu_hours'),'old_qc_pass':False,
       'observed_shape':'3474x10','expected_shape':'10x10',
       'decision':'QUARANTINED_NOT_DATA_SOURCE','method':'new boundary GF10 point-table; original invalid raster retained'}
    prev=core.load(SETTINGS,{})
    if prev.get('quarantine') and prev['quarantine']!=r:raise FileExistsError('Quarantine evidence changed; stop')
    prev['quarantine']=r;core.atomic_json(SETTINGS,prev)
    print(json.dumps(r,indent=2))


def _verify_old_records():
    base,c,g,model,ct=frozen()
    old=core.load(base/'reports'/'task_ledger.json',[])
    st=core.load(SETTINGS,{})
    q=st.get('quarantine')
    for rec in old:
        if rec.get('local_qc_pass'):continue
        if rec.get('superseded_by') and any(t.get('key')==rec['superseded_by'] and t.get('local_qc_pass') for t in old):continue
        if q and rec['key']==q['old_key'] and rec.get('task_id')==q['old_task_id']:continue
        raise RuntimeError('Unreconciled previous GEE task without approved QC: '+rec['key'])
    return old


def _point_features(ee,land,wkt):
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([*( (int(r.grid_x)+.5)*10000,(int(r.grid_y)+.5)*10000 )],proj=wkt),
          {'grid_id':str(r.grid_id),'grid_x':int(r.grid_x),'grid_y':int(r.grid_y)})
        for r in land.itertuples(index=False)])


def _tight_roi(ee,land,wkt):
    x0=int(land.grid_x.min());x1=int(land.grid_x.max())+1
    y0=int(land.grid_y.min());y1=int(land.grid_y.max())+1
    l,b,r,t=x0*10000,y0*10000,x1*10000,y1*10000
    if l < -core.X_LIMIT or r > core.X_LIMIT or b < -core.Y_LIMIT or t > core.Y_LIMIT:
        # The frozen GF10 cell may straddle validity boundary, though centroid
        # remains legitimate. Construct a bounded centroid envelope, not invalid corners.
        l=max(l,-core.X_LIMIT+100);r=min(r,core.X_LIMIT-100)
        b=max(b,-core.Y_LIMIT+100);t=min(t,core.Y_LIMIT-100)
    if r<=l or t<=b:raise ValueError('No EPSG:6933 bounded extent for selected land cells')
    return ee.Geometry.Rectangle([l,b,r,t],proj=wkt,geodesic=False)


def submit(args):
    import pandas as pd
    base,c,g,model,ct=frozen()
    if args.confirm!=c['run_id']+'_BOUNDARY_V4' and args.execute:raise ValueError('Exact confirmation required for v4')
    plan=ROOT/'reports'/'projection_plan_v4.csv'
    if not plan.is_file():raise FileNotFoundError('Run inspect first; strict frozen 10km plan')
    p=pd.read_csv(plan)
    key=args.key
    existing=core.load(REG,[])
    if key=='auto':
        used={r['key'] for r in existing}
        old=core.load(base/'reports'/'task_ledger.json',[])
        used.update(r['key'] for r in old if r.get('local_qc_pass') and r.get('family')=='merit' and not r.get('pilot'))
        z=p.loc[~p.tile_key.isin(used)]
        if z.empty:raise ValueError('No remaining unsubmitted GF10 tiles')
        key=str(z.iloc[0].tile_key)
    if key=='merit_1097_367_10_TABLE_PILOT':
        tile=core.Tile(1097,367);mode='POINT_TABLE';pilot=True
    else:
        z=p[p.tile_key==key]
        if len(z)!=1:raise ValueError('Key absent or duplicate in frozen plan')
        row=z.iloc[0];tile=core.Tile(int(row.tile_x0),int(row.tile_y0),int(row.tile_size));mode=core.projected_mode(tile);pilot=False
        if key=='merit_-1740_-240_10' and not core.load(SETTINGS,{}).get('quarantine'):
            raise RuntimeError('Quarantine failed 3474x10 v3 raster first; do not overwrite it')
        if mode=='POINT_TABLE' and not core.load(SETTINGS,{}).get('table_pilot_passed'):
            raise RuntimeError('Must pass independent Wuhan point-table vs Gate C benchmark first')
    if any(r['key']==key for r in existing):raise ValueError('Already registered; cannot spend duplicate EECU')
    land=core.validate_frozen_subset(g,tile)
    info={'key':key,'mode':mode,'n_expected_land':len(land),'bounds':tile.bounds,'GF10_sha256':c['grid_sha256'],'pilot':pilot}
    if not args.execute:
        print(json.dumps({'status':'DRY_RUN_NO_GEE','preview':info},indent=2));return
    _verify_old_records()
    ee=_ee(c)
    for r in existing:
        s=state(ee,r)
        if s['state'] not in ('SUCCEEDED','COMPLETED') or not r.get('local_qc_pass') or s['eecu_hours'] is None:
            raise RuntimeError('Previous v4 task unfinished/unchecked, stop at '+r['key'])
    previous=core.load(base/'reports'/'task_ledger.json',[])
    spent=sum(float(t.get('eecu_hours') or 0) for t in previous)+sum(state(ee,t)['eecu_hours'] for t in existing)
    if spent>float(c.get('static_spend_limit_h',700)):
        raise RuntimeError('Prior EECU exceeds budget; no new submission')
    wkt=c['output_crs_wkt']
    if mode=='POINT_TABLE':
        # Never use the invalid full 10x10 projected rectangle near antimeridian.
        roi=_tight_roi(ee,land,wkt)
        image=model.merit(ee,roi,wkt)
        result=image.reduceRegions(collection=_point_features(ee,land,wkt),reducer=ee.Reducer.first(),
                                   crs=wkt,crsTransform=model.TRANSFORM_10,tileScale=4)
        filename='CEE_V4_'+key+'_POINTS'
        task=ee.batch.Export.table.toDrive(collection=result,description=filename,
                          folder=c['drive_folder'],fileNamePrefix=filename,fileFormat='CSV',
                          selectors=['grid_id','grid_x','grid_y',*ct.MERIT_BANDS])
    else:
        roi=ee.Geometry.Rectangle(core.pixel_centers_region(tile),proj=wkt,geodesic=False)
        full=ee.Geometry.Rectangle(tile.bounds,proj=wkt,geodesic=False)
        image=model.merit(ee,full,wkt).unmask(-9999)
        filename='CEE_V4_'+key+'_IMAGE'
        task=ee.batch.Export.image.toDrive(image=image,description=filename,
             folder=c['drive_folder'],fileNamePrefix=filename,
             region=roi,crs=wkt,crsTransform=model.TRANSFORM_10,
             maxPixels=1000,fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    task.start();ts=task.status()
    r={**info,'file':filename+('.csv' if mode=='POINT_TABLE' else '.tif'),
       'task_id':task.id,'operation':ts.get('name') or f"projects/{c['project']}/operations/{task.id}",
       'local_qc_pass':False,'submitted_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
       'project':c['project'],'run_id':c['run_id']+'_BOUNDARY_V4'}
    existing.append(r);core.atomic_json(REG,existing)
    print(json.dumps(r,indent=2))
    print('ONE TASK SUBMITTED. Download original result, execute audit before any other task.')


def audit_task(args):
    import numpy as np
    from rasterio.windows import Window
    import rasterio
    base,c,g,model,ct=frozen();ee=_ee(c)
    records=core.load(REG,[]);matching=[r for r in records if r['key']==args.key]
    if len(matching)!=1:raise ValueError('Unknown v4 task key')
    r=matching[0];s=state(ee,r)
    if s['state'] not in ('SUCCEEDED','COMPLETED'):raise ValueError('EE task must succeed before reading downloaded export')
    if s['eecu_hours'] is None:raise ValueError('Unknown EECU usage; retain task without approval')
    p=pathlib.Path(args.file or ROOT/'downloads'/r['file'])
    if not p.is_file():raise FileNotFoundError('Download original result to '+str(p))
    tile=core.Tile(*[int(x) for x in r['key'].replace('_TABLE_PILOT','').split('_')[1:]])
    if r['mode']=='POINT_TABLE':
        result=audit.audit_boundary_csv(p,g,tile,ct.MERIT_BANDS)
        if r['pilot']:
            import pandas as pd
            ref=pathlib.Path(args.reference or base.parent/'gee_ceegf10_v1'/'reports'/'gate_c_drive_tifs'/'gate_c_merit_v2_wuhan_10x10.tif')
            if not ref.is_file():raise FileNotFoundError('Independent Wuhan Gate C raster missing: '+str(ref))
            z=pd.read_csv(p)
            with rasterio.open(ref) as ds:
                if ds.count!=16:raise ValueError('Gate C reference 16 bands required')
                arr=ds.read(masked=True).filled(np.nan)
            pairs=[]
            for row in z.itertuples(index=False):
                gx=int(row.grid_x);gy=int(row.grid_y)
                px=gx-1097;py=9-(gy-367)
                if not (0<=px<10 and 0<=py<10):raise ValueError('Pilot cell out of range')
                vals=np.array([getattr(row,b) if getattr(row,b) is not None else np.nan for b in ct.MERIT_BANDS],dtype='float64')
                actual=arr[:,py,px]
                ok=np.isfinite(vals)&np.isfinite(actual)
                pairs.extend((abs(vals[ok]-actual[ok])/np.maximum(1,abs(actual[ok]))).tolist())
            if len(pairs)<500:raise ValueError('Too few independent Wuhan comparable values')
            result['gate_c_relative_p95']=float(np.percentile(pairs,95))
            result['gate_c_relative_max']=float(np.max(pairs))
            if result['gate_c_relative_p95']>0.01:raise ValueError('Point table does not reproduce independent Wuhan MERIT 16-band Gate C')
            st=core.load(SETTINGS,{})
            st['table_pilot_passed']={'source_key':r['key'],'p95':result['gate_c_relative_p95']}
            core.atomic_json(SETTINGS,st)
    else:result=audit.audit_regular_raster(p,g,tile,ct.MERIT_BANDS)
    r['local_qc_pass']=True;r['audit']=result;r['eecu_hours']=s['eecu_hours']
    core.atomic_json(REG,records)
    result['eecu_hours']=s['eecu_hours'];core.atomic_json(ROOT/'reports'/(r['key']+'.qc.json'),result)
    print(json.dumps(result,indent=2))


def show_status(args):
    base,c,g,model,ct=frozen();ee=_ee(c)
    rows=core.load(REG,[])
    out=[]
    for r in rows:
        s=state(ee,r)
        out.append({'key':r['key'],'state':s['state'],'eecu_hours':s['eecu_hours'],'local_qc_pass':r.get('local_qc_pass'),'mode':r['mode']})
    print(json.dumps(out,indent=2))


def cohort_check(args):
    base,c,g,model,ct=frozen()
    ids=set(g.grid_id.astype(str))
    out=ROOT/'reports'/'cohort_contract.qc.json'
    r=cohort.audit(args.events,ids,out)
    print(json.dumps(r,indent=2))

def main(argv=None):
    p=argparse.ArgumentParser(description='GF10 MERIT boundary-safe GEE v4; no automatic global enqueue')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('inspect');a.add_argument('--plan')
    a=sub.add_parser('quarantine');a.add_argument('--key',required=True)
    a=sub.add_parser('submit');a.add_argument('--key',default='auto');a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('audit');a.add_argument('--key',required=True);a.add_argument('--file');a.add_argument('--reference')
    sub.add_parser('status')
    a=sub.add_parser('cohort-check');a.add_argument('--events',required=True)
    a=p.parse_args(argv)
    return {'inspect':inspect,'quarantine':quarantine,'submit':submit,'audit':audit_task,'status':show_status,'cohort-check':cohort_check}[a.cmd](a)
if __name__=='__main__':main()
