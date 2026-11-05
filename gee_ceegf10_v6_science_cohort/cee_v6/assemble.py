"""Strict partial/global production assemblies from accepted records only."""
from __future__ import annotations
import pathlib,json,numpy as np,pandas as pd
from .common import ROOT,check_grid,writetab,save,sha
from .production import CLOUD,old_context
from .science import BANDS

def merge_verified_weather(downloads,out,allow_partial=False):
    from .common import load
    ledger=load(CLOUD) if CLOUD.exists() else []
    records=[x for x in ledger if x.get('kind')=='PRE_WEATHER_SCREENING' and x.get('local_qc_pass') is True]
    if not records:raise ValueError('No accepted v6 weather tasks; must run download+weather-audit+live-accept')
    planned=pd.read_csv(ROOT/'plans'/'event_requests_v6.csv')
    accepted_keys={z['key'] for z in records}
    if not accepted_keys.issubset(set(planned.request_key)):raise ValueError('Unexpected weather task key in v6 ledger')
    if not allow_partial and len(accepted_keys)!=len(planned):
        raise ValueError(f'Only {len(accepted_keys)} of {len(planned)} event groups have accepted weather; use --allow-partial for pilot')
    frames=[]
    for r in records:
        p=pathlib.Path(downloads)/r['file']
        if not p.exists() or sha(p)!=r['local_file_sha256']:
            raise ValueError('Weather CSV missing or SHA changed: '+str(p))
        f=pd.read_csv(p,dtype={'grid_id':'string','date_utc':'string'})
        if len(f)!=r['n_grid_days']:raise ValueError('Weather CSV row count changed after QC')
        frames.append(f)
    allrows=pd.concat(frames,ignore_index=True)
    if allrows.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate overlapping date-grid extraction')
    dest=pathlib.Path(out)
    writetab(allrows,dest)
    report={'status':'EVENT_M0_ALL_CANDIDATE_TASKS_ACCEPTED' if len(accepted_keys)==len(planned) else 'PARTIAL_M0_PILOT_ONLY',
       'expected_task_groups':len(planned),'accepted_groups':len(accepted_keys),
       'accepted_grid_days':len(allrows),'source_files_sha256':{r['key']:r['local_file_sha256'] for r in records},
       'not_independent_flood_validation':True}
    save(dest.with_suffix('.qc.json'),report)
    return report

def merge_verified_merit(root,out,allow_partial=True):
    import rasterio
    from .common import load
    r,v4,v5,c=old_context(root)
    gate=ROOT/'reports'/'merit_halo_science_gate_v6.json'
    if not gate.exists() or load(gate)['status']!='PASS_20_40_80_HALO_NUMERIC_CONVERGENCE':
        raise ValueError('MERIT science gate not passed')
    registry=load(CLOUD) if CLOUD.exists() else []
    # The 80km convergence reference for a sample tile is already a valid
    # science-buffered source; re-use it to avoid needless EECU repetition.
    accepted=[z for z in registry if z.get('kind') in ('MERIT_FINAL80_SINGLE_TILE','MERIT_BUFFER_CONVERGENCE')
              and z.get('halo_km')==80 and z.get('local_qc_pass') is True]
    if not accepted:raise ValueError('No accepted production MERIT blocks')
    g=check_grid(c['grid_path'])
    lookup={(int(x),int(y)):i for i,(x,y) in enumerate(zip(g.grid_x,g.grid_y))}
    values=np.full((len(g),16),np.nan,dtype='float32')
    seen=set();nonland=0
    for record in accepted:
        path=ROOT/'downloads'/record['file']
        if not path.exists() or sha(path)!=record['local_file_sha256']:
            raise ValueError('MERIT input has changed since independent QC')
        xx,yy,w,h=record['crop']
        with rasterio.open(path) as ds:
            if ds.count!=16 or (ds.width,ds.height)!=(w,h) or ds.crs.to_epsg()!=6933:
                raise ValueError('Invalid MERIT raster shape or crs')
            a=ds.read(masked=True).filled(np.nan)
        for row in range(h):
            for col in range(w):
                key=(xx+col,yy+h-row-1)
                ix=lookup.get(key)
                if ix is None:nonland+=1;continue
                if ix in seen:raise ValueError('Overlapping accepted MERIT production GF10 IDs')
                seen.add(ix);values[ix]=a[:,row,col]
    result=g[['grid_id','grid_x','grid_y','land_area_km2']].copy()
    for n,k in enumerate(BANDS):result[k]=values[:,n]
    if not allow_partial and len(seen)!=len(g):raise ValueError('Global not complete, 14 seams and more blocks pending')
    out=pathlib.Path(out);writetab(result,out)
    report={'status':'MERIT_ALL_GLOBALLY_COMPLETE' if len(seen)==len(g) else 'MERIT_ACCEPTED_TILE_PARTIAL_ONLY',
        'n_registered_grid':len(g),'n_grid_with_accepted_tiles':len(seen),
        'n_uncovered_GF10':len(g)-len(seen),'n_water_only_export_pixels':nonland,
        'n_accepted_production_tasks':len(accepted),'not_flood_observation':True}
    save(out.with_suffix('.qc.json'),report)
    return report
