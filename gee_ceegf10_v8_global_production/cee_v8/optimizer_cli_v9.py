"""Windows CLI for bounded v9 MERIT packing on top of frozen v8 producer."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd
from . import core,optimizer,pilot_v9


def main(argv=None):
    ap=argparse.ArgumentParser('CEE GF10 v9 GEE batch optimization with independent science canary')
    ap.add_argument('--root',default=r'E:\GEE_flooding')
    ap.add_argument('--pkg',default=r'E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106')
    sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ('preview','plan-pilots','approve','promote','status'):
        sub.add_parser(name)
    x=sub.add_parser('tick-pilots');x.add_argument('--storage',choices=('drive','gcs'),default='drive');x.add_argument('--bucket');x.add_argument('--max-inflight',type=int,default=2)
    a=ap.parse_args(argv)
    root=Path(a.root);pkg=Path(a.pkg)
    if a.cmd=='preview':
        src=pkg/'plans'/'merit_batches.csv'
        if not src.is_file():raise FileNotFoundError('First run v8 prepare with frozen source verification')
        r=pd.read_csv(src).to_dict('records');stats=[]
        for factor in (1,2,3,4):
            _,qc=optimizer.pack_safe(r,factor)
            stats.append(qc)
        result={'status':'OFFLINE_PACKING_COUNT_ONLY_NOT_GEE_APPROVED','sizes':stats}
    elif a.cmd=='plan-pilots':result=pilot_v9.create_pilot_plan(root,pkg)
    elif a.cmd=='tick-pilots':result=pilot_v9.tick_pilots(root,pkg,a.storage,a.bucket,a.max_inflight)
    elif a.cmd=='approve':result=pilot_v9.approved_factor(root,pkg)
    elif a.cmd=='promote':result=pilot_v9.promote_v8_plan(root,pkg)
    else:
        p=pkg/'pilot_v9'
        ledger=core.read_json(p/'pilot_ledger.json',{})
        result={'status':'PILOT_TERMINAL_STATES_WITH_REAL_CLOUD_SOURCE_ONLY',
              'n_known':len(ledger),'tasks':[{k:v for k,v in z.items() if k in ('state','factor','stratum','eecu_h','task_id','source_sha256','p95_rel','max_rel','error')} for z in ledger.values()]}
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    return result

if __name__=='__main__':main()
