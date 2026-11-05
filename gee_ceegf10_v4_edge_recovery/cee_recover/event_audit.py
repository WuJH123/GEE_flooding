"""Audit only small event-date asset after task succeeds; no label is uploaded."""
from __future__ import annotations
import argparse,json,math
from . import io
from .run import HOME,conf,ee_init

COUNT_FIELDS={'imerg_n_obs_day':48,'imerg_n_obs_pre7d':336,
              'imerg_n_obs_pre14d':672,'imerg_n_obs_pre30d':1440}

def audit(a):
    c=conf();reg_path=HOME/'reports'/'event_recovery_tasks.json'
    reg=io.load(reg_path,[])
    hits=[z for z in reg if z['key']==a.key]
    if len(hits)!=1:raise ValueError('Cannot audit task outside frozen event ledger')
    rec=hits[0];ee=ee_init(c)
    op=ee.data.getOperation(rec['operation']);meta=op.get('metadata') or {}
    if meta.get('state') not in ('SUCCEEDED','COMPLETED'):
        raise ValueError('Event export not successful; no scientific output available')
    source=ee.FeatureCollection(rec['asset'])
    size=int(source.size().getInfo())
    if size!=int(rec['n_rows_expected']):raise ValueError('Expected number of distinct GF10 dates did not arrive')
    feats=source.limit(101).getInfo()['features']
    if len(feats)!=size:raise ValueError('Event feature collection larger than audit safety limit')
    keys=[];coverage=[];era5=0;fail=[]
    for feature in feats:
        d=feature.get('properties') or {}
        grid=str(d.get('grid_id'))
        if not grid or grid=='None':fail.append('missing GF10 ID')
        keys.append(grid)
        for name,num in COUNT_FIELDS.items():
            v=d.get(name)
            if v is None or not math.isfinite(float(v)) or float(v)>num+1e-3:
                fail.append(f'{grid}:invalid {name}={v}')
        # Missing observations remain null, never inferred dry zero.
        count=d.get('imerg_n_obs_day')
        rainfall=d.get('imerg_day_mm')
        if count is not None and float(count)!=48 and rainfall is not None:
            fail.append(f'{grid}:incomplete IMERG day has nonnull daily rainfall')
        if d.get('era5_soil_l1_prevday_m3m3') is not None:era5+=1
        coverage.append(count)
    if len(keys)!=len(set(keys)):fail.append('Duplicate grid ID within same date task')
    result={'status':'METHOD_VALUES_QA_PASS_NOT_PHYSICAL_FLOOD_VALIDATION' if not fail else 'FAIL',
           'expected':rec['n_rows_expected'],'n_rows':size,'era5_l1_valid_rows':era5,
           'imerg_day_counts':coverage,'errors':fail[:30],
           'note':'Any incomplete IMERG windows must stay NaN; ERA5 gaps must not be zero-filled'}
    io.atomic(HOME/'reports'/(a.key.replace('/','_')+'.eventqc.json'),result)
    if fail:raise ValueError(json.dumps(result))
    rec['local_qc_pass']=True
    io.atomic(reg_path,reg)
    print(json.dumps(result,indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('--key',required=True)
    audit(p.parse_args())
if __name__=='__main__':main()
