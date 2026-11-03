from pathlib import Path
from .common import read_json

def report(root):
    root=Path(root)
    paths=[root/'reports/cee_all_inventory_v11.json',root/'data/working/cee_all_tiles64_v11/tiles_qc.json']
    for f in (root/'data/derived/cee_all_v11').rglob('run_qc.json') if (root/'data/derived/cee_all_v11').exists() else []:
        paths.append(f)
    for p in ('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020'):
        paths.append(root/'data/derived'/f'hpc_exact_{p}_v2/run_qc.json')
    out=[]
    for p in paths:
        if not p.exists():out.append({'file':str(p),'status':'NOT_DONE'});continue
        try:
            j=read_json(p);out.append({'file':str(p),'status':j.get('status','UNKNOWN'),
              'n_tasks':j.get('n_tasks'),'n_rows':j.get('n_rows')})
        except Exception as e:out.append({'file':str(p),'status':'UNREADABLE','error':str(e)})
    return out
