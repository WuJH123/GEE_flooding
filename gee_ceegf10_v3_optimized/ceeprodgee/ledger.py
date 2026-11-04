"""Ledger of only this version's tasks, not other GEE project tasks."""
from __future__ import annotations
from pathlib import Path
import json,os,tempfile

def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.writing')
    with open(tmp,'w',encoding='utf8') as f:json.dump(obj,f,indent=2,ensure_ascii=False)
    os.replace(tmp,path)

def read_json(path,default=None):
    p=Path(path)
    return json.loads(p.read_text('utf8')) if p.exists() else default

def task_state(ee,op):
    z=ee.data.getOperation(op);m=z.get('metadata') or {}
    s=m.get('batchEecuUsageSeconds',m.get('batch_eecu_usage_seconds'))
    state=m.get('state','UNKNOWN')
    return {'state':state,'eecu_hours':float(s)/3600 if s is not None else None,
            'error':(z.get('error') or {}).get('message')}

def dedupe(registry,task_key):
    if any(x['key']==task_key for x in registry):raise ValueError('Duplicate task key, refusing duplicate EECU')
