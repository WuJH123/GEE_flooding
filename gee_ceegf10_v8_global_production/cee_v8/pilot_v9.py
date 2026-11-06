"""Measured EE canary for 2x2,3x3,4x4 MERIT tile packing.

Only test output compared against independent V7 80km accepted scientific
reference can release a new packing factor. This is a true EE live task, not a
proof generated from synthetic test data. Supports restart by task ledger.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np
from . import core,optimizer,eeops,download,qc,budget_v9


def _write_json_once(path,data):
    path=Path(path)
    if path.exists():raise FileExistsError(f'Immutable pilot already frozen: {path}')
    core.write_json(path,data)


def _accepted_reference(frame):
    """V7 partial product retains every GF10 ID; only measured rows are reference."""
    if 'merit_valid_fraction' not in frame:
        raise ValueError('V7 reference validity band missing')
    measured=frame.loc[frame.merit_valid_fraction.notna()].copy()
    if len(measured)!=863 or measured.grid_id.duplicated().any():
        raise ValueError('V7 accepted MERIT reference must contain exactly 863 unique measured cells')
    return measured


def create_pilot_plan(root,pkg):
    """Create 3 representative real baseline-reference comparisons per size."""
    files=core.root_files(root)
    grid=core.validate_grid(files['grid'])
    gextra=pd.read_parquet(files['grid'],columns=['grid_id','latitude'])
    grid=grid.merge(gextra,on='grid_id',validate='one_to_one')
    grid['parent_x']=(grid.grid_x//10)*10
    grid['parent_y']=(grid.grid_y//10)*10
    grid['parent_tile']='merit_'+grid.parent_x.astype(str)+'_'+grid.parent_y.astype(str)+'_10'
    land=grid.groupby('parent_tile')['grid_id'].agg(lambda a:';'.join(sorted(a.astype(str)))).to_dict()
    all_safe=pd.read_csv(files['v4']/'plans'/'merit_safe_v4.csv').to_dict('records')
    if len(all_safe)!=16860:raise ValueError('Not the immutable V4 safe tile inventory')
    full=[]
    for r in all_safe:
        r['land_ids']=land.get(r['tile_key'])
        if not r['land_ids'] or len(r['land_ids'].split(';'))!=int(r['n_land_cells']):
            raise ValueError('V4 safe tile missing actual land members '+r['tile_key'])
        full.append(r)
    old=files['v7']/'data'/'merit_v7_batch5_accepted_partial.parquet'
    base=pd.read_parquet(old,columns=['grid_id','merit_valid_fraction'])
    base=_accepted_reference(base)[['grid_id']]
    accepted=set(base.grid_id.astype(str))
    ref=grid[grid.grid_id.astype(str).isin(accepted)].copy()
    ref['stratum']='inland'
    ref.loc[ref.land_area_km2.lt(98),'stratum']='coastal'
    ref.loc[ref.latitude.abs().ge(52),'stratum']='high_latitude'
    strata=['coastal','high_latitude','inland']
    missing=[s for s in strata if not (ref.stratum==s).any()]
    if missing:raise ValueError('V7 accepted reference cannot verify essential environment strata '+str(missing))
    selected=[]
    used_by_factor={2:set(),3:set(),4:set()}
    from collections import defaultdict
    grouped={factor:defaultdict(list) for factor in (2,3,4)}
    for parent in full:
        px,py=optimizer._xy(parent)
        for factor in grouped:
            grouped[factor][(px//(factor*10),py//(factor*10))].append(parent)
    merged_cache={factor:{} for factor in grouped}
    for factor in (2,3,4):
        for stratum in strata:
            a=ref.loc[ref.stratum==stratum].sort_values(['grid_x','grid_y'])
            candidates=[]
            for anc in a.itertuples(index=False):
                gx=(int(anc.grid_x)//(factor*10));gy=(int(anc.grid_y)//(factor*10))
                parents=grouped[factor].get((gx,gy),[])
                if not parents:continue
                if (gx,gy) not in merged_cache[factor]:
                    merged_cache[factor][(gx,gy)]=optimizer._group_rows(parents,factor)
                merged=merged_cache[factor][(gx,gy)]
                compare=accepted&set(merged['land_ids'].split(';'))
                if (merged['width']>factor*10 or merged['height']>factor*10 or
                    merged['native_source_megapixels_estimate']>42):continue
                if merged['tile_key'] in used_by_factor[factor]:continue
                candidates.append((len(compare),merged))
            if not candidates:raise ValueError(f'Cannot construct real MERIT {factor}×{factor} {stratum} pilot')
            score,row=max(candidates,key=lambda z:z[0]);row['reference_count_expected']=score
            used_by_factor[factor].add(row['tile_key'])
            row['stratum']=stratum;row['factor']=factor
            selected.append(row)
    p=Path(pkg)/'pilot_v9';p.mkdir(parents=True,exist_ok=True)
    f=p/'pilot_plan.csv'
    if f.exists():raise FileExistsError('Pilot plan already frozen')
    pd.DataFrame(selected).to_csv(f,index=False)
    core.write_json(p/'pilot_plan_qc.json',{
      'status':'LIVE_EE_PILOT_PLAN_NOT_YET_COMPUTED',
      'count':len(selected),'factors':[2,3,4],
      'strata':strata,'reference_V7_SHA256':core.sha(old),
      'pilot_plan_SHA256':core.sha(f),
      'GF10_SHA256':core.GRID_SHA})
    return {'status':'PILOTS_PLANNED_NOT_SUBMITTED','pilot_tasks':len(selected),'path':str(f)}


def _reference_compare(path,row,old):
    import rasterio
    with rasterio.open(path) as ds:a=ds.read(masked=True).filled(np.nan)
    ids=old[old.grid_id.astype(str).isin(row.land_ids.split(';'))]
    if len(ids)<1:raise ValueError('Pilot missing independent V7 reference')
    deltas=[];mismatch=0;bad_bands=0
    for j,band in enumerate(core.BANDS):
        d=[]
        for z in ids.itertuples(index=False):
            xx,yy=map(int,str(z.grid_id).split('_'))
            ix=xx-int(row.crop_x0);iy=int(row.crop_y0)+int(row.height)-yy-1
            actual=float(a[j,iy,ix]);ref=float(getattr(z,band))
            if np.isfinite(actual)!=np.isfinite(ref):mismatch+=1;continue
            if not np.isfinite(ref):continue
            d.append(abs(actual-ref)/max(abs(ref),1.0))
        if d:
            if np.quantile(d,.95)>.005 or max(d)>.02:bad_bands+=1
            deltas.extend(d)
    if not deltas:raise ValueError('No finite numerical pairs for V9 pilot')
    return {'reference_count':len(ids),'p95_rel':float(np.quantile(deltas,.95)),
            'max_rel':float(max(deltas)),'mask_mismatch':mismatch,'n_bad_bands':bad_bands}


def tick_pilots(root,pkg,storage='drive',bucket=None,max_inflight=2):
    """One idempotent live tick; call repeatedly until all candidates terminal."""
    if max_inflight not in (1,2,3):raise ValueError('Pilot concurrency must be 1–3')
    pp=Path(pkg)/'pilot_v9';qcfile=core.read_json(pp/'pilot_plan_qc.json')
    if not qcfile or core.sha(pp/'pilot_plan.csv')!=qcfile['pilot_plan_SHA256']:
        raise ValueError('Untrusted pilot plan')
    download.check_auth(storage,bucket)
    budget=budget_v9.budget_decision(budget_v9.current_month_eecu_hours(core.PROJECT),900,simultaneous=max_inflight)
    if not budget['can_submit']:
        raise RuntimeError('Pilot monthly EECU budget fuse: '+str(budget))
    ee=eeops.initialize()
    cfg=core.read_json(core.root_files(root)['v4']/'config'/'recovery.json')
    if not cfg:raise ValueError('Verified V4 full-WKT config missing')
    wkt=cfg['crs_wkt']
    rows=pd.read_csv(pp/'pilot_plan.csv')
    ledger_file=pp/'pilot_ledger.json'; ledger=core.read_json(ledger_file,{})
    src=core.root_files(root)['v7']/'data'/'merit_v7_batch5_accepted_partial.parquet'
    accepted=pd.read_parquet(src)
    accepted=_accepted_reference(accepted)
    if len(accepted)!=863 or not set(core.BANDS)<=set(accepted):
        raise ValueError('Accepted V7 MERIT 16-band source is not intact')
    live=0
    for r in rows.to_dict('records'):
        name=core.RUN+'_P9_'+r['batch_id'];ent=ledger.get(name)
        if not ent:continue
        if ent['state'] in ('ACCEPTED','QUARANTINED'):continue
        live+=1
        tid=ent.get('task_id')
        if not tid:
            hits=[z for z in ee.data.getTaskList() if z.get('description')==name]
            if len(hits)==1:tid=hits[0].get('id')
            elif len(hits)>1:raise ValueError('Duplicate pilot EE task description')
            if not tid:continue
            ent['task_id']=tid
        t=ee.data.getTaskStatus([tid])
        if not t:continue
        state=t[0].get('state')
        if state in ('COMPLETED','SUCCEEDED'):
            name_prefix=core.RUN+'_P9_'+r['batch_id']
            out=pp/'downloads';out.mkdir(exist_ok=True)
            fn=download.get_source(name_prefix,out,storage,bucket=bucket,kind='merit')
            if fn is None:continue
            try:
                source_row=pd.Series(r)
                base_qc=qc.merit(fn,source_row)
                numeric=_reference_compare(fn,source_row,accepted)
                if numeric['mask_mismatch'] or numeric['n_bad_bands']:
                    raise ValueError('MERIT packing changed previously accepted scientific values')
                operation_name=f'projects/{core.PROJECT}/operations/{tid}'
                op=ee.data.getOperation(operation_name)
                meta=op.get('metadata') or {}
                task_sec=float(meta.get('batchEecuUsageSeconds') or meta.get('batch_eecu_usage_seconds') or
                               t[0].get('batch_eecu_usage_seconds') or t[0].get('batchEecuUsageSeconds') or 0)
                if task_sec<=0:raise ValueError('Missing real EE OperationMetadata EECU seconds for pilot')
                # Task status API commonly provides millisecond start/update times.
                # If missing, inspect canonical OperationMetadata rather than guessing.
                wall=t[0].get('elapsedMs')
                if wall is None:
                    start=t[0].get('start_timestamp_ms');end=t[0].get('update_timestamp_ms')
                    if start and end and int(end)>int(start):wall=int(end)-int(start)
                if wall is None:
                    # Actual start/terminal task timestamps, or canonical operation metadata.
                    from dateutil.parser import isoparse
                    start_iso=meta.get('startTime');end_iso=meta.get('endTime')
                    if start_iso and end_iso:wall=(isoparse(end_iso)-isoparse(start_iso)).total_seconds()*1000
                if wall is None or float(wall)<=0:
                    raise ValueError('No verified task wall time; check EE OperationMetadata')
                ent.update(dict(state='ACCEPTED',source_sha256=core.sha(fn),
                                reference_sha256=core.sha(src),eecu_h=task_sec/3600,
                                task_wall_seconds=float(wall)/1000,
                                stratum=r['stratum'],factor=int(r['factor']),**numeric))
                core.write_json(fn.with_suffix('.qc.json'),{**ent,**base_qc})
            except Exception as ex:ent.update(state='QUARANTINED',error=str(ex))
        elif state in ('FAILED','CANCELLED'):
            ent.update(state='QUARANTINED',error=str(t[0].get('error_message','EE pilot failed')))
        else:ent['state']=state
        ledger[name]=ent;core.write_json(ledger_file,ledger)
    if any(ent.get('state')=='QUARANTINED' for ent in ledger.values()):
        return {'status':'PILOT_SCIENTIFIC_QUARANTINE_STOP',
                'n_jobs':len(rows),'n_accepted':sum(z['state']=='ACCEPTED' for z in ledger.values()),
                'n_quarantined':sum(z['state']=='QUARANTINED' for z in ledger.values()),
                'n_active':sum(z['state'] not in ('ACCEPTED','QUARANTINED') for z in ledger.values())}
    for r in rows.to_dict('records'):
        name=core.RUN+'_P9_'+r['batch_id']
        if name in ledger:continue
        if live>=max_inflight:break
        img,roi,_=eeops.build_merit(ee,root,pd.Series(r),wkt)
        task=eeops.export(ee,'merit',img,name,storage,bucket,wkt=wkt,region=roi)
        ledger[name]={'state':'INTENT','source_parent_tiles':r['parent_tiles'],
                      'factor':int(r['factor']),'stratum':r['stratum']}
        core.write_json(ledger_file,ledger)  # durable intent before start
        task.start();st=task.status()
        ledger[name].update(state='QUEUED',task_id=st.get('id') or task.id)
        core.write_json(ledger_file,ledger);live+=1
    return {'status':'PILOTS_LIVE_TICK_NOT_GLOBAL_COMPLETE',
            'n_jobs':len(rows),'n_accepted':sum(z['state']=='ACCEPTED' for z in ledger.values()),
            'n_quarantined':sum(z['state']=='QUARANTINED' for z in ledger.values()),
            'n_active':sum(z['state'] not in ('ACCEPTED','QUARANTINED') for z in ledger.values())}


def approved_factor(root,pkg):
    pp=Path(pkg)/'pilot_v9';ls=core.read_json(pp/'pilot_ledger.json',{})
    want=9
    if len(ls)<want or any(z.get('state') not in ('ACCEPTED','QUARANTINED') for z in ls.values()):
        raise ValueError('Nine MERIT packing pilots must reach a real terminal state')
    records=[z for z in ls.values() if z.get('state')=='ACCEPTED']
    factor=optimizer.choose_factor_from_live(records)
    if factor<2:raise ValueError('No packing factor achieved independent numeric mask/cost/time gate')
    meta={'status':'INDEPENDENT_LIVE_MERIT_PACKING_PILOT_PASS',
          'approved_max_pack_factor':factor,'n_real_pilots':len(records),
          'record_sha256':core.sha(pp/'pilot_ledger.json'),
          'no_false_global_completion':True}
    core.write_json(pp/'pilot_approval.json',meta)
    return meta


def promote_v8_plan(root,pkg):
    """Atomic pre-registration replacement of V8 MERIT plan only after live gate."""
    pp=Path(pkg)/'pilot_v9';gate=core.read_json(pp/'pilot_approval.json')
    if gate is None or gate.get('status')!='INDEPENDENT_LIVE_MERIT_PACKING_PILOT_PASS':
        raise ValueError('Cannot promote without immutable independent live MERIT pilot')
    if core.sha(pp/'pilot_ledger.json')!=gate['record_sha256']:
        raise ValueError('Pilot evidence changed after scientific approval')
    pl=Path(pkg)/'plans';src=pl/'merit_batches.csv';report=pl/'frozen_plan_qc.json'
    db=Path(pkg)/'reports'/'v8_production.sqlite'
    if db.exists():raise ValueError('V8 already registered: do not rewrite a live task plan')
    q=core.read_json(report)
    if q is None or core.sha(src)!=q['merit_plan_sha256']:
        raise ValueError('Original V8 plan source SHA mismatch')
    data=pd.read_csv(src).to_dict('records')
    if not data or not all('land_ids' in x for x in data):
        raise ValueError('Original member identities missing')
    fac=int(gate['approved_max_pack_factor'])
    packed,diag=optimizer.pack_safe(data,fac)
    backup=pl/'merit_batches_unpacked_v8.csv'
    if backup.exists():raise FileExistsError('Optimized plan already exists')
    backup.write_bytes(src.read_bytes())
    pd.DataFrame(packed).to_csv(src,index=False)
    q['merit_plan_sha256']=core.sha(src)
    q['merit_packing_factor_verified']=fac
    q['merit_unpacked_plan_sha256']=core.sha(backup)
    q['merit_live_pilot_evidence_sha256']=gate['record_sha256']
    q['merit_packing_audit']=diag
    core.write_json(report,q)
    core.write_json(pl/'merit_packing_release_qc.json',{**gate,**diag,
        'source_rows_SHA256':core.sha(backup),'final_plan_SHA256':core.sha(src)})
    return {'status':'MERIT_LIVE_VALIDATED_PACKING_PROMOTED','source_tasks':len(data),
            'packed_tasks':len(packed),'source_land_cells':diag['n_unique_land_cells'],
            'factor':fac}
