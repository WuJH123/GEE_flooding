"""Event-only GEE 10 km extraction with frozen date plan and one-task budget gates.

Not automatically launched. Uses same v3 official meteorological band model.
Keeps case-vs-unreported-exposure labels entirely out of GEE exports.
"""
import argparse,pathlib,json
from . import io,geometry
from .run import HOME,conf,ee_init
LEDGER=HOME/'reports'/'event_recovery_tasks.json'

def run(a):
    import pandas as pd
    c=conf()
    path=HOME/'plans'/'event_gee_tasks_v4.csv'
    gp=HOME/'plans'/'event_gf10_days_v4.parquet'
    cohort=HOME/'plans'/'frozen_case_control_gf10_utc_v4.parquet'
    if not all(p.exists() for p in [path,gp,cohort]):
        raise FileNotFoundError('Build and QA real matched case/control cohort before any event extraction')
    tasks=pd.read_csv(path)
    row=tasks.loc[tasks.tile_key==a.key]
    if len(row)!=1:raise ValueError('Must select a known immutable event task key; no auto submission')
    item=row.iloc[0]
    f=pd.read_parquet(gp)
    sample=f.loc[(f.date_utc==item.date_utc)&(f.tile_x0==item.tile_x0)&(f.tile_y0==item.tile_y0)]
    if len(sample)!=int(item.n_unique_grid_days):raise ValueError('Event task count not conserved')
    expected=int((item.n_unique_grid_days))
    meta={'status':'DRY_RUN_NO_EECU','key':a.key,'date':str(item.date_utc),
          'n_unique_grid_days':expected,'n_10km_tiles':1,
          'project':c['project'],'cost_stage':'METHOD_VALIDATED_NOT_CASE_CONTROL_YET'}
    print(json.dumps(meta,indent=2))
    if not a.execute:return
    if a.confirm!=c['run_id']:raise ValueError('Explicit V4 run_id required')
    if (not (HOME/'reports'/'event_cohort_input_qc.json').exists()):
        raise ValueError('No separately audited cohort QC')
    if expected>100:raise ValueError('Unexpected event tile >100 sampled grid-days')
    from ceeprodgee import ee_model
    ee=ee_init(c)
    old=io.load(LEDGER,[])
    # One GEE date/tile at a time; account for measured metadata, never treat
    # unavailable usage as zero before authorising additional events.
    spent=[]
    for prev in old:
        if not prev.get('operation'):raise RuntimeError('Unreconciled event submission intent; cannot retry')
        operation=ee.data.getOperation(prev['operation'])
        meta=operation.get('metadata') or {}
        sec=meta.get('batchEecuUsageSeconds',meta.get('batch_eecu_usage_seconds'))
        if sec is None:raise RuntimeError('Previous event task usage unavailable; cost gate closed')
        spent.append(float(sec)/3600)
    if sum(spent)+0.1>300:
        raise RuntimeError('Event-day EECU reserve exhausted; freeze a smaller event plan')
    if any(z['key']==a.key for z in old):raise ValueError('Duplicate event task; no repeated EECU')
    for z in old:
        op=ee.data.getOperation(z['operation']);state=(op.get('metadata') or {}).get('state','UNKNOWN')
        if state not in ('SUCCEEDED','COMPLETED') or not z.get('local_qc_pass'):
            raise RuntimeError('Previous event task not successfully audited')
    left,right,bottom,top=geometry.valid_limits()
    features=[]
    for r in sample.itertuples(index=False):
        x=int(r.grid_x);y=int(r.grid_y)
        box=[x*10000,y*10000,(x+1)*10000,(y+1)*10000]
        if box[0]<left+1 or box[2]>right-1 or box[1]<bottom+1 or box[3]>top-1:
            raise ValueError('Event sample intersects EPSG seam, quarantine and process separately')
        geo=ee.Geometry.Rectangle(box,proj=c['crs_wkt'],geodesic=False)
        features.append(ee.Feature(geo,{'grid_id':str(r.grid_id),'date_utc':str(item.date_utc)}))
    stats=ee_model.event_image(ee,str(item.date_utc)).reduceRegions(
        collection=ee.FeatureCollection(features),reducer=ee.Reducer.mean(),
        crs=c['crs_wkt'],crsTransform=ee_model.TRANSFORM_10,tileScale=4)
    # Long-running batch; avoid client getInfo on dynamic global data.
    key=a.key.replace('-','_')
    asset=f'projects/{c["project"]}/assets/{c["run_id"]}_{key}'
    task=ee.batch.Export.table.toAsset(collection=stats,description=key,assetId=asset)
    record={'key':a.key,'operation':None,'asset':asset,'task_id':task.id,
        'n_rows_expected':expected,'date_utc':str(item.date_utc),
        'input_casecontrol_sha256':io.sha(cohort),'local_qc_pass':False,
        'status':'SUBMISSION_INTENT','submitted_utc':io.stamp()}
    old.append(record);io.atomic(LEDGER,old)
    task.start();s=task.status()
    record['operation']=s.get('name') or f'projects/{c["project"]}/operations/{task.id}'
    record['task_id']=task.id
    record['status']=s.get('state')
    io.atomic(LEDGER,old)
    print('ONE AUDITED CASE-CONTROL EVENT METEOROLOGY TASK SUBMITTED',asset)

def main():
    p=argparse.ArgumentParser();p.add_argument('--key',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--confirm')
    run(p.parse_args())
if __name__=='__main__':main()
