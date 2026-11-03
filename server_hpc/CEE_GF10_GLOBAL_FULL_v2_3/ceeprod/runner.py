"""Completely unattended, resumable all-local GF10 full-global production.

No manual layer names, field selection, file paths or artificial 5000-grid cap.
Job-level parallelism and GDAL worker-level parallelism are separate.
"""
from __future__ import annotations
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import subprocess,sys,os,json,time,threading,traceback
from .shared import read_json,write_json,file_identity
from .discover import discover_all

STAGE=('worldclim','era5ex','admin','ucdb','hydroatlas','roads','gisd')
RASTERS={'worldclim-bio':19,'worldclim-monthly':84,'grip-density':1,'gmted':5}
VECTORS=('admin0','admin1','ucdb','basin','river','roads')


def _write_stage(root,stage,report):
    out=Path(root)/'reports/cee_full_v2/stages'/f'{stage}.json'
    write_json(out,report)


def _preexisting_jobs():
    try:import psutil
    except ImportError:return []
    active=[]
    current=os.getpid()
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==current:continue
        try:
            text=' '.join(p.info.get('cmdline') or []).lower()
            if '-m ceeall' in text and any(w in text for w in (' raster',' gisd',' era5ex',' vector-link')):
                active.append({'pid':p.pid,'cmd':text[:150]})
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return active


def plan(root):
    root=Path(root)
    from ceeall.inventory import inventory
    from ceeall.common import verify_frozen_grid
    _,qc=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',True)
    inv=inventory(root/'CEE数据',root/'reports/cee_full_v2/source_inventory.csv')
    staged=discover_all(root)
    report={'status':'PLAN_SOURCE_DISCOVERY_NO_HEAVY_JOB_STARTED','grid':qc,'inventory':inv,
            'staged_vector_sources':staged,'raster_expected':RASTERS,
            'policy':'35 original downloads, GEE=0, full 715 tiles, no manual placeholders',
            'has_source_errors_before_staging':bool(staged['errors'])}
    write_json(root/'reports/cee_full_v2/plan.json',report)
    return {'output':str(root/'reports/cee_full_v2/plan.json'),
        'n_inventory_files':inv['file_count'],'n_grid':qc['n_cells'],
        'n_discovered_vector_sources':len(staged['sources'])}


def stage(root,cap_gb=150,only_family=None):
    """All-local stages with actionable per-family errors and resume-safe QC.

    Deliberately checks GISD30's 7-Zip dependency before starting any
    expensive WorldClim/GDB archive work. Does NOT touch derived Parquet.
    """
    root=Path(root)
    from ceeall.staging import stage_family
    from .doctor import rar_preflight
    if only_family is not None and only_family not in STAGE:
        raise ValueError(f'Unknown source archive family: {only_family}')
    # Fails early if this full-data job cannot process the 12 GISD30 RARs.
    if only_family is None or only_family=='gisd':
        pre=rar_preflight(root,require_tool=True)
        _write_stage(root,'gisd_dependency_preflight',pre)
    selected=[only_family] if only_family else STAGE
    results={}
    for fam in selected:
        started=time.monotonic();print('[stage] '+fam,flush=True)
        try:
            z=stage_family(root/'CEE数据',root/'data/staged/cee_all',fam,
                cap_gb=cap_gb,first=None)
            results[fam]={'status':'ALL_LOCAL_SOURCE_ARCHIVES_STAGED',
                'source_archives':len(z),'entries':z,'seconds':time.monotonic()-started}
            _write_stage(root,'staged_'+fam,results[fam])
            print(f'[stage completed] {fam}; archive_count={len(z)}',flush=True)
        except Exception as exc:
            error={'status':'SOURCE_STAGE_FAILED_NO_DERIVED_DATA_MODIFIED',
                   'family':fam,'error_type':type(exc).__name__,'error':str(exc),
                   'traceback':traceback.format_exc()[-10000:],
                   'action':'Check 7-Zip, corrupt archive, disk space or stage-file QC; do not delete completed GF10 Parquet.'}
            _write_stage(root,'staged_'+fam+'_failed',error)
            raise RuntimeError(f'STAGING FAILED family={fam}: {type(exc).__name__}: {exc}; '
                               f'see reports/cee_full_v2/stages/staged_{fam}_failed.json') from exc
    if only_family:
        return {'status':'ONLY_ONE_SOURCE_FAMILY_STAGED', 'family':only_family, 'archives':len(results[only_family]['entries'])}
    discovery=discover_all(root)
    write_json(root/'reports/cee_full_v2/vector_source_autodetect.json',discovery)
    if discovery['errors']:
        raise ValueError('Automatic provider vector detection incomplete: '+str(discovery['errors']))
    return {'archive_families_staged':len(results),'vector_families_detected':len([k for k in discovery['sources'] if k in VECTORS]), 'ucdb_theme_layers':len(discovery['sources'].get('ucdb_attribute_layers',[]))}

def _complete(root,family,source):
    from ceeall.common import fidentity
    from pyarrow import parquet as pq
    path=Path(root)/'data/derived/cee_all_v11'/family/source.stem
    q=path/'run_qc.json';job=path/'job.json'
    if not q.is_file() or not job.is_file():return False
    z=read_json(q);spec=read_json(job).get('spec',{})
    if not (z.get('status')=='FULL_TILES_NATIVE_EXACT_NEEDS_LAND_QA' and
       z.get('n_tasks')==715 and z.get('n_rows')==1_395_471 and
       spec.get('source')==fidentity(source)):
        return False
    tiles=list((path/'tiles').glob('tile_*.parquet'))
    if len(tiles)!=715:return False
    return True


def _subprocess_raster(root,family,source,workers,logs):
    env=os.environ.copy()
    env.update({'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
                'GDAL_NUM_THREADS':'1','PYTHONPATH':str(Path(__file__).parents[1])})
    name=family+'_'+source.stem
    log=Path(logs)/(name+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-m','ceeall','--root',str(root),'raster',
          '--family',family,'--source',str(source),'--workers',str(workers),
          '--max-tiles','0','--max-sources','0']
    started=time.monotonic()
    with log.open('w',encoding='utf8',errors='replace') as output:
        cp=subprocess.run(args,env=env,cwd=Path(__file__).parents[1],
                         stdout=output,stderr=subprocess.STDOUT)
    if cp.returncode!=0:
        tail=log.read_text('utf8',errors='replace')[-3500:]
        raise RuntimeError(f'Global {family}/{source.name} failed (exit {cp.returncode}): '+tail)
    if not _complete(root,family,source):
        raise ValueError('Raster subprocess exited but GLOBAL 715 tile output did not pass QC '+str(source))
    return {'family':family,'source':source.name,'log':str(log),
            'elapsed_s':time.monotonic()-started,'status':'FULL_GLOBAL_SOURCE_PASS'}


def _monitor(root,stop,period=15):
    import psutil,csv
    path=Path(root)/'reports/cee_full_v2/resource_monitor.csv';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        if path.stat().st_size==0:w.writerow(['utc','cpu_pct','ram_used_gb','ram_total_gb',
             'disk_read_mb_per_s','disk_write_mb_per_s','python_process_count'])
        psutil.cpu_percent(interval=None)
        previous=psutil.disk_io_counters()
        previous_t=time.monotonic()
        samples=0
        while not stop.wait(period):
            vm=psutil.virtual_memory();now=time.monotonic()
            io=psutil.disk_io_counters();elapsed=max(.001,now-previous_t)
            n=sum(1 for x in psutil.process_iter(['name']) if 'python' in (x.info['name'] or '').lower())
            cpu=psutil.cpu_percent(interval=None)
            readrate=(io.read_bytes-previous.read_bytes)/1e6/elapsed if io and previous else float('nan')
            writerate=(io.write_bytes-previous.write_bytes)/1e6/elapsed if io and previous else float('nan')
            w.writerow([time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                       cpu,round(vm.used/1e9,2),round(vm.total/1e9,2),
                       round(readrate,2),round(writerate,2),n])
            f.flush();previous=io;previous_t=now;samples+=1
            if samples%4==0:
                print(f'[resource monitor] CPU {cpu:.1f}% RAM {vm.percent:.1f}% read {readrate:.1f}MB/s write {writerate:.1f}MB/s python_processes={n}',flush=True)


def rasters(root,jobs=4,per_job=16):
    root=Path(root)
    if not 1<=jobs<=6 or not 1<=per_job<=32 or jobs*per_job>96:
        raise ValueError('Raster concurrency must be <=96 processes total; recommended 4 x 16 =64')
    from ceeall.raster import candidates
    pairs=[]
    for family,expected in RASTERS.items():
        src=candidates(root,family)
        if len(src)!=expected:
            raise ValueError(f'Expected all {expected} official {family} rasters, found {len(src)}')
        pairs.extend((family,p) for p in src)
    pending=[(fam,p) for fam,p in pairs if not _complete(root,fam,p)]
    print(f'[raster full] inputs={len(pairs)}, cached_complete={len(pairs)-len(pending)}, new={len(pending)}',flush=True)
    started=time.monotonic();report=[]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        tasks={pool.submit(_subprocess_raster,root,family,p,per_job,
              root/'reports/cee_full_v2/logs'): (family,p) for family,p in pending}
        for i,f in enumerate(as_completed(tasks),1):
            r=f.result();report.append(r)
            print(f'[raster full] {i}/{len(pending)} new globally complete: '+r['source'],flush=True)
            if i%4==0:_write_stage(root,'raster_progress',{'status':'IN_PROGRESS','completed':report})
    if not all(_complete(root,f,p) for f,p in pairs):
        raise ValueError('Raster product completeness check failed after dispatch')
    result={'status':'ALL_109_RASTER_SOURCES_GLOBAL_FULL',
      'n_source_products':len(pairs),'n_already_complete':len(pairs)-len(pending),
      'n_new_full':len(report),'raster_jobs':jobs,'workers_per_job':per_job,
      'elapsed_s':time.monotonic()-started}
    _write_stage(root,'raster_all',result)
    return result


def _one_vector(root,family,workers):
    from .vector_full import run
    return run(root,family,workers)


def vectors(root,jobs=2,per_job=16):
    if not 1<=jobs<=3 or not 1<=per_job<=32 or jobs*per_job>64:
        raise ValueError('For native multi-million-feature GDBs use <=64 total workers / <=3 families')
    result={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures={pool.submit(_one_vector,Path(root),f,per_job):f for f in VECTORS}
        for t in as_completed(futures):
            name=futures[t];result[name]=t.result()
            _write_stage(root,'vector_'+name,result[name]);print('[vector] global complete '+name,flush=True)
    return {'status':'ALL_6_VECTOR_FAMILIES_ALL_715_TILES','families':list(result)}


def other_sources(root):
    root=Path(root);res={}
    from .era_wide import run as era
    res['era5ex']=era(root,workers=2);_write_stage(root,'era5ex',res['era5ex'])
    from .gisd_history import run as gisd
    res['gisd30']=gisd(root,workers=8);_write_stage(root,'gisd30',res['gisd30'])
    from .source_attributes import run as attr
    for fam in ('admin0','admin1','ucdb','basin'):
        res['attributes_'+fam]=attr(root,fam);_write_stage(root,'native_attributes_'+fam,res['attributes_'+fam])
    from .observations_full import run as news
    res['groundsource']=news(root);_write_stage(root,'groundsource',res['groundsource'])
    from ceeall.observations import read_flood_catalogue
    flood=root/'data/derived/cee_all_v11/flood_catalogue/qc.json'
    if flood.exists():res['flood_records']=read_json(flood)
    else:res['flood_records']=read_flood_catalogue(root)
    _write_stage(root,'flood_records',res['flood_records'])
    return res


def run_all(root,raster_jobs=4,raster_workers=16,vector_jobs=2,vector_workers=16,stage_only=False):
    import psutil
    root=Path(root)
    active=_preexisting_jobs()
    if active:
        raise RuntimeError('Other old CEE all-data jobs still running; do not write same original outputs concurrently: '+str(active))
    if psutil.virtual_memory().total<90*1e9:
        raise EnvironmentError('Production profile requires >=90GB RAM')
    lock=root/'reports/cee_full_v2/global_run.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    if lock.exists():
        # PowerShell 5.1 may kill the Python child after the first stderr line,
        # bypassing Python's finally and leaving a stale lock. Do NOT unlink
        # anything while a real production process is still alive.
        import re, psutil
        old=lock.read_text(encoding='utf8',errors='replace')
        match=re.search(r'pid=(\d+)',old)
        pid=int(match.group(1)) if match else -1
        active=False
        if pid>0 and psutil.pid_exists(pid):
            try:
                proc=psutil.Process(pid)
                cmd=' '.join(proc.cmdline()).lower()
                active=('ceeprod' in cmd and 'run' in cmd)
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                # On access denial, fail closed rather than risk two producers.
                active=True
        if active:
            raise RuntimeError('A live CEE production process still holds lock '+str(lock)+
                               f' pid={pid}; do not launch another')
        suffix=time.strftime('%Y%m%d_%H%M%S',time.gmtime())
        stale=lock.with_name('global_run.lock.stale_'+suffix)
        if stale.exists():raise FileExistsError('Stale lock archive already exists '+str(stale))
        os.replace(lock,stale)
        print('[stale-lock] old Python process not running; preserved former lock as '+str(stale),flush=True)
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        with os.fdopen(fd,'w') as f:f.write(f'pid={os.getpid()},start={time.time()}')
    except FileExistsError:
        raise RuntimeError('Another production job holds lock '+str(lock)+'; do not delete until its status verified')
    event=threading.Event()
    watch=threading.Thread(target=_monitor,args=(root,event),daemon=True);watch.start()
    try:
        plan(root)
        stage(root)
        if stage_only:return {'status':'SOURCE_STAGING_COMPLETE'}
        from .gridcache import prepare
        geo=prepare(root,workers=min(16,raster_workers));_write_stage(root,'cache',geo)
        r=rasters(root,jobs=raster_jobs,per_job=raster_workers)
        a=other_sources(root)
        v=vectors(root,jobs=vector_jobs,per_job=vector_workers)
        from .assemble_full import run as merge
        m=merge(root)
        from .dictionary import run as make_dictionary
        d=make_dictionary(root);_write_stage(root,'dictionary',d)
        from .quality import summarize
        qc=summarize(root,strict=True)
        write_json(root/'reports/cee_full_v2/latest_completed_run_v22.json',
            {'status':'GLOBAL_STRUCTURAL_PROCESSING_FINISHED_SCIENCE_QA_REQUIRED',
             'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
        return {'status':'ALL_LOCAL_DOWNLOAD_FAMILIES_STRUCTURALLY_PROCESSED_NEEDS_PUBLICATION_SCIENCE_QA',
           'raster':r,'vector':v,'wide':m,'dictionary':d,'audit':qc}
    except Exception as exc:
        write_json(root/'reports/cee_full_v2/failed_stage.json',{
          'status':'PRODUCTION_STOPPED_NO_FALSE_COMPLETION','error_type':type(exc).__name__,
          'error':str(exc),'traceback_tail':traceback.format_exc()[-16000:],
          'detail':'See latest full_run_v22_* log and reports/cee_full_v2/stages/staged_*_failed.json'})
        raise
    finally:
        event.set();watch.join(timeout=3)
        if lock.exists():lock.unlink()
