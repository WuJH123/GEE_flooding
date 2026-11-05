"""Manual, budget-gated GEE production CLI. Never automatically launches a global batch.

No command reads/writes assets from another Cloud project. Existing user GEE
pilot assets and Gate-C GeoTIFFs are read-only provenance, not dependencies.
"""
from __future__ import annotations
import argparse,datetime as dt,json,os,pathlib,sys
from . import contract,grid,coast,ee_model,ledger,qc,edge_safe
ROOT=pathlib.Path(__file__).resolve().parents[1]
CFG=ROOT/'config'/'production.json'
LEDGER=ROOT/'reports'/'task_ledger.json'


def _config():
    if not CFG.is_file():raise SystemExit('First run: python -m ceeprodgee configure --root E:\\GEE_flooding')
    return ledger.read_json(CFG)


def _ee(conf):
    import ee
    ee.Initialize(project=conf['project'])
    return ee


def _wkt():
    from pyproj import CRS
    return CRS.from_epsg(6933).to_wkt(version='WKT1_GDAL')


def configure(args):
    parent=pathlib.Path(args.root)
    old=parent/'gee_ceegf10_v1'/'config'/'local_run.json'
    if not old.exists():raise FileNotFoundError(f'Previous accepted project config not found: {old}')
    prev=ledger.read_json(old)
    actual=pathlib.Path(prev['grid'])
    if not actual.is_file():raise FileNotFoundError(f'Frozen GF10 not present: {actual}')
    g=grid.read_grid(actual,strict=True)
    if args.project and args.project!=prev['project']:raise ValueError('Refuse project switch: this is the existing independent CEE Cloud project')
    if CFG.exists():
        current=_config()
        if current['grid_sha256']!=grid.frozen_sha256(actual) or current['project']!=prev['project']:
            raise FileExistsError('Existing independent config conflicts; do not overwrite')
        print('CONFIG_ALREADY_VERIFIED',CFG);return
    conf={'project':prev['project'],'grid_path':str(actual),'grid_sha256':grid.frozen_sha256(actual),
          'run_id':'CEE_GF10_M0M1M2_EFFICIENT_20261105_V3',
          'drive_folder':'CEE_GF10_M0M1M2_EFFICIENT_20261105_V3',
          'output_crs_wkt':_wkt(),
          'grid_cells':int(len(g)),'land_km2':float(g.land_area_km2.sum()),
          'static_spend_limit_h':700.0, # leave substantial reserve for M0/event panel
          'pilot_only':True,'pilot_merit_passed':False,'pilot_worldcover_passed':False,
          'gshhg_root':str(parent)}
    ledger.atomic_json(CFG,conf)
    print(json.dumps({'status':'CONFIG_CREATED_NO_TASKS_SUBMITTED',
                      'project':conf['project'],'grid_cells':conf['grid_cells'],
                      'grid_sha256':conf['grid_sha256']},indent=2))


def verify(args):
    conf=_config()
    g=grid.read_grid(conf['grid_path'])
    if grid.frozen_sha256(conf['grid_path'])!=conf['grid_sha256']:raise ValueError('GF10 altered')
    missing=[]
    for p in ['GATE_BC_M1_M2_4BLOCK_ACCEPTANCE_20261104_CN.md']:
        if not (ROOT/'reference'/p).exists():missing.append(p)
    try: sources=coast.discover_gshhg(conf['gshhg_root']); coast_files=list(map(str,sources.values()))
    except FileNotFoundError:coast_files=[]
    result={'status':'FROZEN_GF10_PASS','project':conf['project'],'grid_cells':len(g),
            'coast_shapefiles':coast_files,'worldcover_can_run':len(coast_files)==4,
            'missing_reference_optional':missing}
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if args.strict_coast and not coast_files:raise RuntimeError('Cannot run land-clipped WorldCover without GSHHG Full L1-L4')


def _selected_ids(path):
    import pandas as pd
    if not path or not pathlib.Path(path).exists():raise FileNotFoundError('Urban study cohort ID file needed; freeze independently of flood labels')
    p=pathlib.Path(path)
    frame=pd.read_parquet(p,columns=['grid_id']) if p.suffix.lower()=='.parquet' else pd.read_csv(p,usecols=['grid_id'])
    return list(frame.grid_id.astype(str).unique())


def plan(args):
    conf=_config();g=grid.read_grid(conf['grid_path'])
    selected=_selected_ids(args.study_ids) if args.scope=='study' else None
    p=grid.make_plan(g,args.family,selected)
    n_work=int(p.n_work_pixels.sum());n_actual=int(p.n_land_cells.sum())
    estimate=contract.budget_projection(n_work,args.family)
    out=ROOT/'plans'/f'{args.family}_{args.scope}.csv'
    out.parent.mkdir(parents=True,exist_ok=True)
    p.to_csv(out,index=False)
    report={'family':args.family,'scope':args.scope,'plan':str(out),'tasks':len(p),
            'work_cells_including_ocean':n_work,'land_cells_selected':n_actual,
            'baseline_eecu_estimate':estimate,'global_submit_allowed':False,
            'note':'Planning never starts EE; benchmark one real bounded export and stop if cost cap exceeded'}
    ledger.atomic_json(out.with_suffix('.json'),report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


def _one_tile(args,conf):
    if args.pilot:
        # Wuhan Gate-C anchor; same x/y as independently downloaded source.
        if args.family=='merit':return (1097,367,10)
        return (1097,367,5)
    if not args.plan or not args.tile_key:raise ValueError('For production, --plan path and --tile-key (or auto) required')
    import pandas as pd
    frame=pd.read_csv(args.plan)
    if args.tile_key=='auto':
        submitted={r['key'] for r in ledger.read_json(LEDGER,[])}
        # Choose first outstanding tile in a frozen plan. Empty plans stop safely.
        frame=frame.loc[~frame.tile_key.isin(submitted)]
        if frame.empty:raise ValueError('No unsubmitted tiles in frozen plan')
        item=frame.iloc[:1]
    else:
        item=frame.loc[frame.tile_key==args.tile_key]
    if len(item)!=1:raise ValueError('tile-key not unique/present')
    row=item.iloc[0]
    if row.family!=args.family:raise ValueError('family differs from frozen plan')
    return int(row.tile_x0),int(row.tile_y0),int(row.tile_size)


def _active_guard(ee,entries,replacing=None):
    # Failed source exports are NEVER accepted as data. Exception: a verified
    # known bad task may be explicitly superseded by the *one* queued retry.
    registry={x['key']:x for x in entries}
    for x in entries:
        if not x.get('operation'):
            raise RuntimeError('Previous task missing its original operation: '+x['key'])
        live=ledger.task_state(ee,x['operation'])
        if live['state'] not in ('SUCCEEDED','COMPLETED'):
            raise RuntimeError('Pending/failed previous task: '+x['key']+' '+str(live))
        target=x.get('superseded_by')
        if target:
            if target==replacing and x.get('quarantine') and not x.get('local_qc_pass'):
                # Only within the explicit one-task edge-repair operation.
                continue
            accepted=registry.get(target)
            if not accepted or not accepted.get('local_qc_pass'):
                raise RuntimeError('Rejected export has no QC-passed replacement: '+x['key'])
            continue
        if not x.get('local_qc_pass'):
            raise RuntimeError('Previous task not accepted by local data QC: '+x['key'])


def submit(args):
    c=_config()
    if not args.execute:
        print('DRY_RUN: no EE EECU usage. Add --execute only after reviewing selected tile.');return
    if args.confirm!=c['run_id']:raise ValueError('Explicit exact run ID confirmation required')
    if args.family=='worldcover' and not args.pilot and not c.get('pilot_worldcover_passed'):
        raise RuntimeError('WorldCover pilot GeoTIFF has not passed this implementation equivalence QA')
    if args.family=='merit' and not args.pilot and not c.get('pilot_merit_passed'):
        raise RuntimeError('MERIT pilot GeoTIFF has not passed this implementation equivalence QA')
    x,y,n=_one_tile(args,c)
    if args.family=='worldcover' and n!=5:raise ValueError('Gate C proved only 5x5 WorldCover blocks')
    if args.family=='merit' and n!=10:raise ValueError('Gate C proved only 10x10 MERIT blocks')
    g=grid.read_grid(c['grid_path'])
    subset=g[g.grid_x.between(x,x+n-1)&g.grid_y.between(y,y+n-1)]
    if subset.empty:raise ValueError('No frozen non-Antarctic positive-land cells in tile')
    geom=grid.tile_export_geometry(x,y,n,subset[['grid_x','grid_y']].itertuples(index=False,name=None))
    if geom['kind']=='edge_csv':
        if args.family!='merit':
            raise RuntimeError('Edge CSV support is scientifically validated only for MERIT; WorldCover belongs on the server')
        return _submit_merit_edge(args,c,g,subset,geom)
    if args.family=='worldcover':
        gfiles=coast.discover_gshhg(c['gshhg_root'])
        gj,measured=coast.prepare_land_tile(gfiles,grid.tile_bounds(x,y,n),float(subset.land_area_km2.sum()))
        if measured<=0:raise ValueError('GSHHG land geometry empty')
    else:gj=None
    entries=ledger.read_json(LEDGER,[])
    key=f'{args.family}_{x}_{y}_{n}'
    ledger.dedupe(entries,key)
    if not args.pilot:
        # Only one job at a time, with explicit local QC per preceding output.
        live_ee=_ee(c)
        _active_guard(live_ee,entries)
        # Read live cost; a null EECU value is NOT zero consumption.
        live_costs=[ledger.task_state(live_ee,z['operation']).get('eecu_hours') for z in entries]
        if any(v is None for v in live_costs):
            raise RuntimeError('Prior EECU usage unavailable; cannot authorize another task')
        spent=sum(live_costs)
        # Forecast the *pre-registered plan*, never silently assume every
        # frozen global cell is a relevant urban flood study cell.
        import pandas as pd
        selected_plan=pd.read_csv(args.plan)
        if selected_plan.family.nunique()!=1 or selected_plan.family.iloc[0]!=args.family:
            raise ValueError('Study plan source family conflict')
        future=contract.budget_projection(int(selected_plan.n_work_pixels.sum()),args.family)['eecu_hours_high']
        if spent+future>c['static_spend_limit_h']:
            raise RuntimeError('Conservative all-global cost forecast exceeds 700h static reserve. Freeze urban cohort instead.')
    ee=_ee(c)
    # Compute on the entire exact tile, but limit the export *region* to
    # pixel centres to avoid EE's historical 10x11 edge rounding.
    compute_roi=ee.Geometry.Rectangle(grid.tile_bounds(x,y,n),proj=c['output_crs_wkt'],geodesic=False)
    export_roi=ee.Geometry.Rectangle(geom['roi'],proj=c['output_crs_wkt'],geodesic=False)
    landgeo=ee.Geometry(gj,geodesic=False) if gj is not None else None
    image=(ee_model.merit(ee,compute_roi,c['output_crs_wkt']) if args.family=='merit'
           else ee_model.worldcover(ee,compute_roi,landgeo,c['output_crs_wkt']))
    image=image.unmask(-9999)
    filename=f'CEE_{c["run_id"]}_{key}'
    task=ee.batch.Export.image.toDrive(image=image,description=filename,
        folder=c['drive_folder'],fileNamePrefix=filename,region=export_roi,
        crs=c['output_crs_wkt'],crsTransform=ee_model.TRANSFORM_10,
        maxPixels=2e6,fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized':True,'noData':-9999})
    task.start()
    status=task.status()
    entry={'key':key,'project':c['project'],'run_id':c['run_id'],
           'family':args.family,'pilot':bool(args.pilot),'tile_x0':x,'tile_y0':y,'tile_size':n,
           'file':filename+'.tif','export_format':'GeoTIFF','task_id':task.id,'operation':status.get('name') or f"projects/{c['project']}/operations/{task.id}",
           'state':status.get('state'),'local_qc_pass':False,
           'submitted_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
           'bands':list(contract.frozen_bands(args.family)),
           'gf10_sha256':c['grid_sha256']}
    entries.append(entry);ledger.atomic_json(LEDGER,entries)
    print(json.dumps(entry,indent=2))
    print('ONLY ONE BOUNDED TASK SUBMITTED. Download GeoTIFF to downloads/ and run audit before next tile.')



def _submit_merit_edge(args,conf,g,subset,geometry):
    """Only projected-domain boundary cells, exact centre keyed CSV export.

    No image-region export across +/-180 degrees. Reject previous corrupted
    3474x10 tile via explicit acknowledgment; immutable old ledger preserved.
    """
    x,y,n=geometry['tile']
    original=f'merit_{x}_{y}_{n}'
    entries=ledger.read_json(LEDGER,[])
    prior=[r for r in entries if r.get('key')==original]
    key=original
    if prior:
        key=edge_safe.validate_reject_and_quarantine(
            entries,original,args.repair_ack,args.bad_tif)
    if geometry['partial_projection_domain']:
        # A 10km cell partially outside the projection is not a valid full-cell
        # observation. It requires a separate geodesic scientific validation.
        print('QC_NOTE: some accepted GF10 geometry extends beyond EPSG:6933 projected bounds; output is partial-domain')
    ee=_ee(conf)
    _active_guard(ee,entries,replacing=key if prior else None)
    # Preserve existing budget constraints. Failed jobs still count in EECU.
    spent=[]
    for record in entries:
        v=ledger.task_state(ee,record['operation'])['eecu_hours']
        if v is None:raise RuntimeError('Actual previous EECU unavailable; cannot authorize task')
        spent.append(v)
    import pandas as pd
    plan=pd.read_csv(args.plan)
    forecast=contract.budget_projection(int(plan.n_work_pixels.sum()),'merit')['eecu_hours_high']
    if sum(spent)+forecast>conf['static_spend_limit_h']:
        raise RuntimeError('Conservative full-plan cost exceeds configured static EECU reserve')
    # Only the frozen-land cell pixels, using a compact *inside-projection*
    # region for expensive source computation. Input points use exact GF10 pixel
    # centres. The CSV will have only actual frozen GF10 identifiers.
    comp_roi=ee.Geometry.Rectangle(geometry['roi'],proj=conf['output_crs_wkt'],geodesic=False)
    image=ee_model.merit(ee,comp_roi,conf['output_crs_wkt']).unmask(-9999)
    points=[]
    for row in subset[['grid_x','grid_y','grid_id']].itertuples(index=False):
        gx=int(row.grid_x);gy=int(row.grid_y)
        xy=[(gx+.5)*contract.CELL_METERS,(gy+.5)*contract.CELL_METERS]
        point=ee.Geometry.Point(xy,proj=conf['output_crs_wkt'])
        points.append(ee.Feature(point,{'grid_id':str(row.grid_id)}))
    if len(points)!=geometry['expected_cells']:raise ValueError('GF10 edge candidate count mismatch')
    samples=image.sampleRegions(
        collection=ee.FeatureCollection(points),
        properties=['grid_id'],
        projection=ee.Projection(conf['output_crs_wkt'],ee_model.TRANSFORM_10),
        tileScale=4,geometries=False)
    filename=f'CEE_{conf["run_id"]}_{key}'
    # Table export does not accept image `region`, removing the dateline wrap.
    job=ee.batch.Export.table.toDrive(
        collection=samples,description=filename,
        folder=conf['drive_folder'],fileNamePrefix=filename,
        selectors=['grid_id',*contract.MERIT_BANDS],fileFormat='CSV')
    job.start();st=job.status()
    entry={'key':key,'original_tile_key':original,'project':conf['project'],
        'run_id':conf['run_id'],'family':'merit','pilot':False,
        'tile_x0':x,'tile_y0':y,'tile_size':n,
        'file':filename+'.csv','export_format':'CSV',
        'expected_grid_ids':geometry['grid_ids'],
        'n_expected_grid_ids':len(geometry['grid_ids']),
        'partial_projection_domain':geometry['partial_projection_domain'],
        'roi_projected':geometry['roi'],
        'task_id':job.id,
        'operation':st.get('name') or f"projects/{conf['project']}/operations/{job.id}",
        'state':st.get('state'),'local_qc_pass':False,
        'submitted_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'bands':list(contract.MERIT_BANDS),'gf10_sha256':conf['grid_sha256']}
    entries.append(entry)
    ledger.atomic_json(LEDGER,entries)
    print(json.dumps({'submission':'ONE EDGE TABLE TASK ONLY',**entry},indent=2))

def status(args):
    c=_config();entries=ledger.read_json(LEDGER,[])
    if not entries:print('NO_TASKS_IN_NEW_VERSION');return
    ee=_ee(c)
    total=0.
    for item in entries:
        st=ledger.task_state(ee,item['operation']) if item.get('operation') else {'state':'UNKNOWN'}
        item['state']=st['state'];item['error']=st.get('error'); item['eecu_hours']=st.get('eecu_hours')
        total+=st.get('eecu_hours') or 0.
    ledger.atomic_json(LEDGER,entries)
    print(json.dumps({'tasks':[{k:v for k,v in row.items() if k in ('key','state','eecu_hours','error','local_qc_pass')} for row in entries],
                      'eecu_total_h':total,'static_budget_ceiling_h':c['static_spend_limit_h']},indent=2))


def _baseline(family,x,y,n,root):
    import rasterio
    from rasterio.windows import from_bounds
    old=pathlib.Path(root)/'gee_ceegf10_v1'/'reports'
    if family=='merit':
        path=old/'gate_c_drive_tifs'/'gate_c_merit_v2_wuhan_10x10.tif'
    else:path=old/'gate_c_mosaics'/'worldcover_wuhan_10x10.tif'
    if not path.exists():return None
    with rasterio.open(path) as ds:
        # first pilot is Wuhan lower-left 5x5, so window is row 5..9 col 0..4.
        bounds=grid.tile_bounds(x,y,n)
        win=from_bounds(*bounds,transform=ds.transform).round_offsets().round_lengths()
        if win.width!=n or win.height!=n:raise ValueError('Gate-C baseline geometry not aligned')
        return ds.read(window=win,masked=True).filled(float('nan'))


def audit(args):
    import numpy as np
    entries=ledger.read_json(LEDGER,[])
    matches=[e for e in entries if e['key']==args.key]
    if len(matches)!=1:raise ValueError('Cannot find task key in the isolated task registry')
    rec=matches[0];c=_config()
    filepath=pathlib.Path(args.file or ROOT/'downloads'/rec['file'])
    # Exports may omit GeoTIFF descriptive strings; our immutable submitted
    # per-task registry contains the exact EE band order for that purpose.
    state=ledger.task_state(_ee(c),rec['operation'])
    if state['state'] not in ('SUCCEEDED','COMPLETED'):
        raise ValueError('Cannot mark non-successful EE task as validated')
    if rec.get('export_format')=='CSV':
        result=edge_safe.check_edge_csv(filepath,rec['expected_grid_ids'])
        if rec.get('partial_projection_domain'):
            result['partial_projection_domain']=True
            result['publication_ready']=False
            result['requires_edge_footprint_review']=True
        rec['local_qc_pass']=True;rec['qc']=result
        ledger.atomic_json(LEDGER,entries)
        ledger.atomic_json(ROOT/'reports'/(rec['key']+'.qc.json'),result)
        print(json.dumps(result,indent=2));return
    result=qc.check_raster(filepath,rec['family'],rec['tile_x0'],rec['tile_y0'],rec['tile_size'],
                           expected_manifest=rec['bands'])
    if rec['pilot']:
        parent=pathlib.Path(c['gshhg_root']).resolve()
        base=_baseline(rec['family'],rec['tile_x0'],rec['tile_y0'],rec['tile_size'],parent)
        if base is None:raise FileNotFoundError('Independent Gate-C Wuhan GeoTIFF missing. Pilot cannot be approved from self-consistency alone.')
        import rasterio
        with rasterio.open(filepath) as ds:current=ds.read(masked=True).filled(np.nan)
        if base.shape!=current.shape:raise ValueError('Gate-C output band count/shape mismatch')
        good=np.isfinite(base)&np.isfinite(current)
        if not np.any(good):raise ValueError('Pilot has no common finite output')
        rel=np.abs(current[good]-base[good])/np.maximum(1,np.abs(base[good]))
        pct95=float(np.percentile(rel,95)); mx=float(np.max(rel))
        result['gate_c_relative_p95']=pct95
        result['gate_c_relative_max']=mx
        # This is an algorithm equivalence test; 1% p95 allows minor rasterization.
        if pct95>0.01:raise ValueError(f'Independent Gate-C numeric agreement failed: p95={pct95}')
    rec['local_qc_pass']=True;rec['qc']=result
    ledger.atomic_json(LEDGER,entries)
    if rec['pilot']:
        c['pilot_'+rec['family']+'_passed']=True
        ledger.atomic_json(CFG,c)
    dest=ROOT/'reports'/(rec['key']+'.qc.json');ledger.atomic_json(dest,result)
    print(json.dumps(result,indent=2))


def merge(args):
    """Join processed bounded rasters to immutable registry; missing remains null."""
    import pandas as pd
    import numpy as np
    import rasterio
    c=_config();g=grid.read_grid(c['grid_path'])
    registry=[r for r in ledger.read_json(LEDGER,[]) if r['family']==args.family and r.get('local_qc_pass')]
    if not registry:raise ValueError('No QA-passed tile outputs')
    columns=list(contract.frozen_bands(args.family));seen=set();blocks=[]
    for r in registry:
        p=ROOT/'downloads'/r['file']
        if not p.exists():raise FileNotFoundError(p)
        if r.get('export_format')=='CSV':
            edge_safe.check_edge_csv(p,r['expected_grid_ids'])
            block=pd.read_csv(p,encoding='utf-8-sig',dtype={'grid_id':str})
            for key in columns:
                block[key]=pd.to_numeric(block[key],errors='raise').replace(-9999,float('nan'))
            ids=list(block.grid_id.astype(str))
            if len(ids)!=len(set(ids)) or set(ids)&seen:raise ValueError('Duplicate GF10 IDs across CSV and GeoTIFF')
            seen.update(ids)
            blocks.append(block[['grid_id',*columns]])
            continue
        qc.check_raster(p,args.family,r['tile_x0'],r['tile_y0'],r['tile_size'],expected_manifest=r.get('bands'))
        with rasterio.open(p) as ds:
            img=ds.read(masked=True).filled(float('nan'))
            rr,cc=np.indices((ds.height,ds.width))
            xx=r['tile_x0']+cc;yy=r['tile_y0']+(ds.height-1-rr)
            keys=np.char.add(np.char.add(xx.astype(str),'_'),yy.astype(str)).ravel()
            if any(k in seen for k in keys):raise ValueError('Overlapping exported tile GF10 keys')
            seen.update(keys)
            block=pd.DataFrame({'grid_id':keys})
            for i,n in enumerate(columns):block[n]=img[i].ravel()
            blocks.append(block)
    b=pd.concat(blocks,ignore_index=True)
    final=g[['grid_id','grid_x','grid_y','land_area_km2']].merge(b,on='grid_id',how='left',validate='one_to_one')
    if len(final)!=contract.GRID_N:raise ValueError('GF10 row count changed')
    out=ROOT/'data'/(f'gf10_{args.family}_partial_verified.parquet')
    out.parent.mkdir(parents=True,exist_ok=True);final.to_parquet(out,index=False)
    report={'file':str(out),'n_grid':len(final),'n_export_cells':len(b),
            'n_land_grid_with_source':int(final[columns[0]].notna().sum()),
            'all_global_complete':bool(final[columns[0]].notna().all()),
            'note':'Missing values stay NaN. A partial product is NOT global completion.'}
    ledger.atomic_json(out.with_suffix('.qc.json'),report)
    print(json.dumps(report,indent=2))



def preview_edge(args):
    c=_config();g=grid.read_grid(c['grid_path'])
    x,y,n=map(int,(args.x,args.y,args.n))
    subset=g[g.grid_x.between(x,x+n-1)&g.grid_y.between(y,y+n-1)]
    if subset.empty:raise ValueError('No GF10 actual land cells')
    shape=grid.tile_export_geometry(x,y,n,subset[['grid_x','grid_y']].itertuples(index=False,name=None))
    print(json.dumps(shape,indent=2))

def event_pilot(args):
    c=_config()
    if not args.execute:
        print('EVENT PILOT DRY RUN; add --execute for one 2023 test date');return
    if args.confirm!=c['run_id']:raise ValueError('Explicit run-id confirmation required')
    from . import ee_model
    ee=_ee(c);g=grid.read_grid(c['grid_path'])
    # Fixed methodological probe cells; not selected using flood outcomes.
    targets=[(1102,372),(702,238),(-2,573),(-743,619)]
    lookup={(int(a),int(b)):(a,b) for a,b in zip(g.grid_x,g.grid_y)}
    feat=[]
    for x,y in targets:
        if (x,y) not in lookup:continue
        geom=ee.Geometry.Rectangle(grid.tile_bounds(x,y,1),proj=c['output_crs_wkt'],geodesic=False)
        feat.append(ee.Feature(geom,{'grid_id':f'{x}_{y}','date_utc':args.date}))
    img=ee_model.event_image(ee,args.date)
    sample=img.reduceRegions(collection=ee.FeatureCollection(feat),reducer=ee.Reducer.mean(),
                             crs=c['output_crs_wkt'],scale=10000,tileScale=4)
    key='event_method_'+args.date.replace('-','')
    entries=ledger.read_json(LEDGER,[])
    ledger.dedupe(entries,key)
    asset=f"projects/{c['project']}/assets/{c['run_id']}_{key}"
    task=ee.batch.Export.table.toAsset(collection=sample,description=key,assetId=asset)
    task.start();s=task.status()
    entries.append({'key':key,'operation':s.get('name') or f"projects/{c['project']}/operations/{task.id}",'task_id':task.id,'asset':asset,
                    'kind':'EVENT_METHOD_ONLY','project':c['project'],'local_qc_pass':False})
    ledger.atomic_json(LEDGER,entries)
    print('ONE EVENT METHOD PILOT TASK SUBMITTED, NO EVENT-CASE DATA EXTRACTED',asset)


def plan_events(args):
    import pandas as pd
    c=_config();g=grid.read_grid(c['grid_path'])
    path=pathlib.Path(args.events)
    if not path.exists():raise FileNotFoundError(path)
    frame=pd.read_parquet(path,columns=['grid_id','date_utc']) if path.suffix.lower()=='.parquet' else pd.read_csv(path,usecols=['grid_id','date_utc'])
    rows,work=grid.event_plan_from_records(frame,g)
    out=ROOT/'plans';out.mkdir(exist_ok=True)
    rows.to_parquet(out/'event_grid_days.parquet',index=False)
    work.to_csv(out/'event_task_plan.csv',index=False)
    print(json.dumps({'n_event_grid_days':len(rows),'n_task_groups':len(work),
                      'event_plan':str(out/'event_task_plan.csv'),
                      'note':'Only spatial meteorological covariates. Original paired controls and case labels remain separate.'},indent=2))


def event_submit(args):
    """Explicit ONE task for a pre-registered case/control date and 10x10 block."""
    import pandas as pd
    c=_config()
    if not args.execute:
        print('EVENT DATE TASK DRY RUN. Add --execute and --confirm to spend EECU.');return
    if args.confirm!=c['run_id']:raise ValueError('Need exact run ID')
    plan_path=ROOT/'plans'/'event_task_plan.csv'
    gp=ROOT/'plans'/'event_grid_days.parquet'
    if not plan_path.exists() or not gp.exists():raise FileNotFoundError('Run event-plan first')
    work=pd.read_csv(plan_path)
    matches=work.loc[work.tile_key==args.key]
    if len(matches)!=1:raise ValueError('Task not uniquely identified in frozen cohort')
    item=matches.iloc[0]
    rows=pd.read_parquet(gp)
    chosen=rows.loc[(rows.date_utc==item.date_utc)&(rows.tile_x0==item.tile_x0)&(rows.tile_y0==item.tile_y0)]
    if len(chosen)!=int(item.n_unique_grid_days) or not len(chosen):raise ValueError('Event cohort counts changed')
    ee=_ee(c);features=[]
    for row in chosen.itertuples(index=False):
        x=int(row.grid_x);y=int(row.grid_y)
        geo=ee.Geometry.Rectangle(grid.tile_bounds(x,y,1),proj=c['output_crs_wkt'],geodesic=False)
        features.append(ee.Feature(geo,{'grid_id':str(row.grid_id),'date_utc':str(row.date_utc)}))
    im=ee_model.event_image(ee,str(item.date_utc))
    res=im.reduceRegions(collection=ee.FeatureCollection(features),reducer=ee.Reducer.mean(),
                         crs=c['output_crs_wkt'],scale=10000,tileScale=4)
    tag=str(item.tile_key).replace('-','')
    asset=f"projects/{c['project']}/assets/{c['run_id']}_{tag}"
    regs=ledger.read_json(LEDGER,[]);ledger.dedupe(regs,args.key)
    task=ee.batch.Export.table.toAsset(collection=res,description=tag,assetId=asset)
    task.start();st=task.status()
    reg={'key':args.key,'project':c['project'],'run_id':c['run_id'],
         'task_id':task.id,'operation':st.get('name') or f"projects/{c['project']}/operations/{task.id}",
         'asset':asset,'n_expected':len(chosen),'kind':'EVENT_GRID_DATE',
         'date_utc':str(item.date_utc),'local_qc_pass':False}
    regs.append(reg);ledger.atomic_json(LEDGER,regs)
    print(json.dumps(reg,indent=2))


def audit_event_asset(args):
    import math
    c=_config();ee=_ee(c);registry=ledger.read_json(LEDGER,[])
    rows=[r for r in registry if r['key']==args.key and r.get('kind')=='EVENT_GRID_DATE']
    if len(rows)!=1:raise ValueError('Unknown event task')
    rec=rows[0];status=ledger.task_state(ee,rec['operation'])
    if status['state'] not in ('SUCCEEDED','COMPLETED'):raise ValueError('Event task not succeeded')
    data=ee.FeatureCollection(rec['asset']).getInfo()['features']
    if len(data)!=rec['n_expected']:raise ValueError('Event table count mismatch')
    ids=[v['properties']['grid_id'] for v in data]
    if len(set(ids))!=len(ids):raise ValueError('Event table duplicate IDs')
    expected={r['key']:r for r in registry}
    bad=[]
    for item in data:
        prop=item['properties']
        for k in ('imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre30d'):
            if k not in prop or prop[k] is None:bad.append((prop.get('grid_id'),k,'MISSING'))
        if prop.get('imerg_n_obs_day') is not None and prop['imerg_n_obs_day']!=48:
            bad.append((prop.get('grid_id'),'imerg_n_obs_day',prop.get('imerg_n_obs_day')))
        if prop.get('imerg_n_obs_pre7d') is not None and prop['imerg_n_obs_pre7d']!=336:
            bad.append((prop.get('grid_id'),'imerg_n_obs_pre7d',prop.get('imerg_n_obs_pre7d')))
        if prop.get('imerg_n_obs_pre30d') is not None and prop['imerg_n_obs_pre30d']!=1440:
            bad.append((prop.get('grid_id'),'imerg_n_obs_pre30d',prop.get('imerg_n_obs_pre30d')))
    report={'key':args.key,'status':'PASS' if not bad else 'FAIL_MISSING_METEOROLOGY',
            'n_rows':len(data),'bad':bad[:20],'note':'Observation completeness verified; NOT flood outcome validation'}
    ledger.atomic_json(ROOT/'reports'/(args.key+'.eventqc.json'),report)
    if bad:raise ValueError(json.dumps(report))
    rec['local_qc_pass']=True;rec['eecu_hours']=status.get('eecu_hours')
    ledger.atomic_json(LEDGER,registry)
    print(json.dumps(report,indent=2))

def main(argv=None):
    p=argparse.ArgumentParser(description='CEE GF10 v2 production, zero automatic global submissions')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('configure');a.add_argument('--root',required=True);a.add_argument('--project')
    a=sub.add_parser('verify');a.add_argument('--strict-coast',action='store_true')
    a=sub.add_parser('plan');a.add_argument('--family',required=True,choices=['merit','worldcover']);a.add_argument('--scope',choices=['all','study'],default='all');a.add_argument('--study-ids')
    a=sub.add_parser('submit');a.add_argument('--family',required=True,choices=['merit','worldcover']);a.add_argument('--pilot',action='store_true');a.add_argument('--plan');a.add_argument('--tile-key');a.add_argument('--execute',action='store_true');a.add_argument('--confirm');a.add_argument('--repair-ack');a.add_argument('--bad-tif')
    sub.add_parser('status')
    a=sub.add_parser('audit');a.add_argument('--key',required=True);a.add_argument('--file')
    a=sub.add_parser('merge');a.add_argument('--family',choices=['merit','worldcover'],required=True)
    a=sub.add_parser('preview-edge');a.add_argument('--x',type=int,required=True);a.add_argument('--y',type=int,required=True);a.add_argument('--n',type=int,default=10)
    a=sub.add_parser('event-pilot');a.add_argument('--date',default='2023-06-01');a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('event-plan');a.add_argument('--events',required=True)
    a=sub.add_parser('event-submit');a.add_argument('--key',required=True);a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('event-audit');a.add_argument('--key',required=True)
    args=p.parse_args(argv)
    return {'configure':configure,'verify':verify,'plan':plan,'submit':submit,'status':status,
            'audit':audit,'merge':merge,'preview-edge':preview_edge,'event-pilot':event_pilot,
            'event-plan':plan_events,'event-submit':event_submit,'event-audit':audit_event_asset}[args.cmd](args)
if __name__=='__main__':main()
