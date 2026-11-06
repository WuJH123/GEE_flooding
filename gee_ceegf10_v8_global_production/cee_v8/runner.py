"""One-process, journaled, bounded global GEE production scheduler.

This is a client-side controller, NOT ChatGPT background work. Must remain running
on the user's Windows computer. A task is counted only when GEE succeeded AND
its downloaded file passed independent local QC and exact immutable key tests.
"""
from __future__ import annotations
import pathlib,json,datetime as dt,time,sqlite3,traceback
import pandas as pd
from . import core,plan,eeops,download,qc,optimizer,budget_v9

ACTIVE=('INTENT','QUEUED','READY','RUNNING','PENDING','SUBMITTED')
FAILED=('FAILED','CANCELLED','CANCELED')

def get_paths(root,pkg):
 root=pathlib.Path(root);pkg=pathlib.Path(pkg)
 return core.root_files(root),pkg/'plans',pkg/'reports'/'v8_production.sqlite',pkg/'downloads'

def register(root,pkg):
 paths,pl,db_path,_=get_paths(root,pkg)
 q=core.read_json(pl/'frozen_plan_qc.json')
 if not q or q.get('status')!='FROZEN_V8_GLOBAL_PRODUCTION_PLAN_READY_NOT_CLOUD_COMPLETE':raise ValueError('V8 immutable plan not verified')
 if q['gf10_sha256']!=core.GRID_SHA or core.sha(pl/'weather_grid_days.parquet')!=q['weather_plan_sha256'] or core.sha(pl/'merit_batches.csv')!=q['merit_plan_sha256']:
  raise ValueError('V8 input plan SHA has changed since frozen!')
 if q.get('merit_packing_factor_verified'):
  gate=core.read_json(pathlib.Path(pkg)/'pilot_v9'/'pilot_approval.json')
  if (not gate or gate.get('approved_max_pack_factor')!=q['merit_packing_factor_verified'] or
      gate.get('record_sha256')!=q.get('merit_live_pilot_evidence_sha256') or
      core.sha(pathlib.Path(pkg)/'pilot_v9'/'pilot_ledger.json')!=gate['record_sha256']):
   raise ValueError('Packed MERIT plan lacks real source-independent science evidence')
 c=core.dbopen(db_path);now=core.timestamp()
 merit=pd.read_csv(pl/'merit_batches.csv')
 weather=pd.read_csv(pl/'weather_batches.csv')
 for _,r in merit.iterrows():
  key=str(r.batch_id)
  c.execute('INSERT OR IGNORE INTO jobs(key,family,state,source_sha,description,n_rows,updated) VALUES(?,?,?,?,?,?,?)',
   (key,'merit','PLANNED',q['merit_plan_sha256'],str(r.tile_key),int(r.n_land_cells),now))
 for _,r in weather.iterrows():
  key=str(r.batch_id)
  c.execute('INSERT OR IGNORE INTO jobs(key,family,state,source_sha,description,n_rows,updated) VALUES(?,?,?,?,?,?,?)',
   (key,'weather','PLANNED',q['weather_plan_sha256'],str(r.date_min)+'..'+str(r.date_max),int(r.n_rows),now))
 canary=pd.read_parquet(pl/'canary_rows.parquet')
 ck=canary.batch_id.iloc[0]
 c.execute('INSERT OR IGNORE INTO jobs(key,family,state,source_sha,description,n_rows,updated) VALUES(?,?,?,?,?,?,?)',
  (ck,'canary','PLANNED',q['v7_accepted_weather_sha256'],'SOURCE_IDENTICAL_V7_THREE_DATE_46_ROW_EQUIVALENCE',len(canary),now))
 c.commit()
 return {'status':'V8_DURABLE_JOBS_REGISTERED','merit_remaining':len(merit),
 'weather_batches':len(weather),'canary_rows':len(canary),'sqlite':str(db_path)}

def membership(pkg,key):
 p=pathlib.Path(pkg)/'plans'
 if key.startswith('W8_CANARY_'):return pd.read_parquet(p/'canary_rows.parquet')
 split=p/'adaptive_splits'/(key+'.parquet')
 if split.exists():return pd.read_parquet(split)
 a=pd.read_parquet(p/'weather_grid_days.parquet')
 f=a[a.batch_id.eq(key)].copy()
 if len(f)==0:raise KeyError('No immutable weather request group '+key)
 return f

def merit_row(pkg,key):
 plans=pathlib.Path(pkg)/'plans'
 p=plans/'merit_batches.csv'
 child=plans/'adaptive_merit'/(key+'.csv')
 if child.exists():
  f=pd.read_csv(child)
 else:f=pd.read_csv(p)
 a=f[f.batch_id.eq(key)]
 if len(a)!=1:raise KeyError('Missing/duplicate MERIT safe block '+key)
 return a.iloc[0]

def report(c):
 rows=c.execute('SELECT family,state,COUNT(*) n,SUM(COALESCE(eecu_h,0)) eecu FROM jobs GROUP BY family,state').fetchall()
 total=c.execute('SELECT SUM(COALESCE(eecu_h,0)) FROM jobs').fetchone()[0] or 0
 return {'status':'V8_CHECKPOINT_REAL_QC_ONLY','known_v8_eecu_h':float(total),
  'groups':[dict(z) for z in rows],
  'merit_safe_tiles_complete':not bool(c.execute("SELECT 1 FROM jobs WHERE family='merit' AND state NOT IN ('ACCEPTED','SPLIT') LIMIT 1").fetchone()),
  'global_merit_all_GF10_complete':False,
  'all_event_weather_complete':not bool(c.execute("SELECT 1 FROM jobs WHERE family in ('weather','canary','canary_child') AND state NOT IN ('ACCEPTED','SPLIT') LIMIT 1").fetchone()),
  'merit_seam450_status':'QUARANTINED_PENDING_INDEPENDENT_NUMERIC_VERIFICATION'}

def _cloud_one(ee,root,pkg,row,mode,bucket=None):
 paths,pl,db_path,_=get_paths(root,pkg)
 c=paths['v4']/'config'/'recovery.json';config=core.read_json(c)
 if not config or config.get('project')!=core.PROJECT or config.get('grid_sha256')!=core.GRID_SHA:raise ValueError('Upstream v4 not approved')
 wkt=config['crs_wkt'];key=row['key'];kind=row['family'];name=core.RUN+'_'+key
 if kind in ('weather','canary','canary_child'):
  members=membership(pkg,key)
  collection=eeops.build_weather(ee,root,members,wkt)
  return eeops.export(ee,'weather',collection,name,mode,bucket)
 source=merit_row(pkg,key)
 image,region,bbox=eeops.build_merit(ee,root,source,wkt)
 return eeops.export(ee,'merit',image,name,mode,bucket,wkt=wkt,region=region)

def _reconcile(c,ee,max_errors=2):
 changes=0
 for row in c.execute("SELECT * FROM jobs WHERE state IN ('INTENT','QUEUED','READY','RUNNING','PENDING','SUBMITTED')").fetchall():
  key=row['key'];state=row['state'];operation=row['operation']
  if not operation:
   # EE's Python API may not assign task.id until AFTER .start(). An INTENT
   # without ID is NOT proof that no export was launched. Reconcile exactly by
   # immutable description, never issue another start for the same job.
   try:
    statuses=ee.data.getTaskList()
    desc=core.RUN+'_'+key
    hits=[x for x in statuses if x.get('description')==desc]
    if len(hits)>1:raise RuntimeError('Duplicated EE description: '+desc)
    if len(hits)==1 and hits[0].get('id'):
     tid=hits[0]['id'];op=hits[0].get('name') or f'projects/{core.PROJECT}/operations/{tid}'
     core.transition(c,key,state,'QUEUED',operation=op,task_id=tid);changes+=1
   except Exception:pass
   continue
  try:remote,eecu,error=eeops.task_status(ee,row)
  except Exception as exc:
   raise RuntimeError('Live GEE status unavailable for '+key+'; stop scheduling rather than blindly adding tasks') from exc
  mapped={'SUCCEEDED':'SUCCEEDED','COMPLETED':'SUCCEEDED','RUNNING':'RUNNING',
   'READY':'READY','PENDING':'PENDING','SUBMITTED':'QUEUED','FAILED':'FAILED','CANCELLED':'FAILED','CANCELED':'FAILED'}.get(remote)
  if mapped is None:continue
  if mapped!=state:core.transition(c,key,state,mapped,eecu_h=eecu,error=error);changes+=1
  elif eecu is not None and row['eecu_h'] is None:
   c.execute('UPDATE jobs SET eecu_h=? WHERE key=?',(eecu,key));c.commit()
 return changes

def _download_qc(c,root,pkg,mode,bucket):
 accepted=0;quarantined=0;_,pl,_,out=get_paths(root,pkg)
 for row in c.execute('SELECT * FROM jobs WHERE state="SUCCEEDED"').fetchall():
  key=row['key'];kind=row['family'];name=core.RUN+'_'+key
  if row['eecu_h'] is None:continue
  try:
   path=download.get_source(name,out,mode,bucket=bucket,kind='weather' if kind!='merit' else 'merit')
  except Exception as exc:
   # Transient Drive/GCS network or authorization failure is NOT scientific QC failure.
   # Retain SUCCEEDED and try again after credentials/connectivity are repaired.
   continue
  if path is None:continue
  try:
   if kind=='merit':result=qc.merit(path,merit_row(pkg,key))
   else:
    ref=pd.read_parquet(pl/'accepted_v7_weather.parquet') if kind in ('canary','canary_child') else None
    if ref is not None and kind=='canary_child':
     keys=set(zip(membership(pkg,key).grid_id.astype(str),membership(pkg,key).date_utc.astype(str)))
     ref=ref[[ (str(g),str(d)) in keys for g,d in zip(ref.grid_id,ref.date_utc) ]]
    result=qc.weather(path,membership(pkg,key),reference=ref)
   core.write_json(path.with_suffix('.qc.json'),result)
   core.transition(c,key,'SUCCEEDED','ACCEPTED',local_sha=core.sha(path),file_name=path.name)
   accepted+=1
  except Exception as ex:
   core.transition(c,key,'SUCCEEDED','QUARANTINED',error=type(ex).__name__+': '+str(ex)[:500]);quarantined+=1
 return accepted,quarantined

def _choose_jobs(c,kind,limit,canary_ok):
 if not canary_ok:return c.execute("SELECT * FROM jobs WHERE family IN ('canary','canary_child') AND state='PLANNED' LIMIT ?",(limit,)).fetchall()
 # Keep both static/dynamic work moving. Each tick uses at least one of each
 # family where available; no 16k MERIT job queue pushed at once.
 if limit==1:
  return c.execute("SELECT * FROM jobs WHERE family IN ('weather','merit') AND state='PLANNED' ORDER BY key LIMIT 1").fetchall()
 a=c.execute("SELECT * FROM jobs WHERE family='merit' AND state='PLANNED' ORDER BY key LIMIT ?",(max(1,limit//2),)).fetchall()
 b=c.execute("SELECT * FROM jobs WHERE family='weather' AND state='PLANNED' ORDER BY key LIMIT ?",(limit-len(a),)).fetchall()
 if len(a)+len(b)<limit:
  a+=c.execute("SELECT * FROM jobs WHERE family='merit' AND state='PLANNED' AND key NOT IN ("+','.join('?' for _ in a)+") ORDER BY key LIMIT ?",tuple([z['key'] for z in a]+[limit-len(a)-len(b)])).fetchall() if a else c.execute("SELECT * FROM jobs WHERE family='merit' AND state='PLANNED' ORDER BY key LIMIT ?",(limit-len(b),)).fetchall()
 return (a+b)[:limit]

def _adaptive_failure_handling(c,pkg):
    """Bounded weather graph bisect; preserve failed parent and disjoint descendants.

    An unexpectedly large *MERIT* failure is quarantined instead of executing
    an unverified new scientific algorithm. One-row weather errors quarantine.
    """
    result=[]
    for row in c.execute('SELECT * FROM jobs WHERE state="FAILED"').fetchall():
        k=row['key']
        if row['family']=='merit':
            source=merit_row(pkg,k)
            parents=str(source.get('parent_tiles',''))
            if not parents or ';' not in parents:
                core.transition(c,k,'FAILED','QUARANTINED',error=row['error'] or 'Failed single original 10x10 parent; needs scientific review')
                continue
            base=pathlib.Path(pkg)/'plans'/'merit_batches_unpacked_v8.csv'
            if not base.exists():raise ValueError('Missing frozen original MERIT parent mapping for adaptive split')
            children=optimizer.split_packed_parent(source,pd.read_csv(base).to_dict('records'))
            out=pathlib.Path(pkg)/'plans'/'adaptive_merit';out.mkdir(parents=True,exist_ok=True)
            for child in children:
                cid=child['batch_id'];fp=out/(cid+'.csv')
                if not fp.exists():pd.DataFrame([child]).to_csv(fp,index=False)
                c.execute('INSERT OR IGNORE INTO jobs(key,family,state,parent,source_sha,description,n_rows,depth,updated) VALUES(?,?,?,?,?,?,?,?,?)',
                    (cid,'merit','PLANNED',k,core.sha(fp),'ADAPTIVELY_SPLIT_PACKED_MERIT_'+k,
                     int(child['n_land_cells']),int(row['depth'])+1,core.timestamp()))
                result.append(cid)
            core.transition(c,k,'FAILED','SPLIT')
            continue
        if row['depth']>=6:
            core.transition(c,k,'FAILED','QUARANTINED',error=row['error'] or 'No scientifically verified automatic recovery')
            continue
        members=membership(pkg,k)
        if len(members)<2:
            core.transition(c,k,'FAILED','QUARANTINED',error=row['error'] or 'Single-row physics/source failure')
            continue
        left,right=plan.split_weather_frame(members)
        out=pathlib.Path(pkg)/'plans'/'adaptive_splits';out.mkdir(parents=True,exist_ok=True)
        for half in (left,right):
            pairs=sorted(half.grid_id.astype(str)+'@'+half.date_utc.astype(str))
            child=('C8S_' if row['family'] in ('canary','canary_child') else 'W8S_')+core.hashkey(*pairs)
            fp=out/(child+'.parquet')
            if not fp.exists():half.assign(batch_id=child).to_parquet(fp,index=False)
            if child==k:raise ValueError('Adaptive split cycle')
            c.execute('INSERT OR IGNORE INTO jobs(key,family,state,parent,source_sha,description,n_rows,depth,updated) VALUES(?,?,?,?,?,?,?,?,?)',
             (child,'canary_child' if row['family'] in ('canary','canary_child') else 'weather','PLANNED',k,core.sha(fp),'ADAPTIVELY_SPLIT_'+k,len(half),int(row['depth'])+1,core.timestamp()))
            result.append(child)
        core.transition(c,k,'FAILED','SPLIT')
    return result


def _unresolved(c):
 return c.execute('SELECT COUNT(*) FROM jobs WHERE state IN ("INTENT","SUCCEEDED","QUARANTINED")').fetchone()[0]

def _submit(c,ee,root,pkg,row,mode,bucket):
 task=_cloud_one(ee,root,pkg,row,mode,bucket)
 key=row['key'];identity=task.id
 # Write INTENT before task.start(); crash cannot cause untracked duplicate.
 core.transition(c,key,'PLANNED','INTENT',task_id=identity,file_name=core.RUN+'_'+key+('.tif' if row['family']=='merit' else '.csv'))
 task.start()
 st=task.status()
 identity=st.get('id') or getattr(task,'id',None)
 if identity is None and not st.get('name'):
  raise RuntimeError('EE task started but returned no ID/operation; INTENT retained for live reconciliation')
 op=st.get('name') or f'projects/{core.PROJECT}/operations/{identity}'
 core.transition(c,key,'INTENT','QUEUED',operation=op,task_id=identity)
 return key

def _legacy_canary(c):
 r=c.execute("SELECT state FROM jobs WHERE family='canary' LIMIT 1").fetchone()
 if not r:return False
 if r[0]=='ACCEPTED':return True
 if r[0]!='SPLIT':return False
 children=c.execute("SELECT state FROM jobs WHERE family='canary_child'").fetchall()
 return bool(children) and all(z[0] in ('ACCEPTED','SPLIT') for z in children) and any(z[0]=='ACCEPTED' for z in children)


def one_tick(root,pkg,mode,bucket,max_inflight=5,max_unaccepted=20,budget_used_eecu=None,budget_limit_eecu=900,execute=False):
 if budget_used_eecu is None and execute:raise ValueError('Must provide verified CURRENT MONTH project EECU usage. See Cloud Monitoring, not v7 pilot extrapolation')
 if budget_used_eecu is not None and budget_used_eecu<0:raise ValueError('Budget negative')
 if not 1<=max_inflight<=12:raise ValueError('Unreasonable EE queue concurrency')
 files,pl,db_path,_=get_paths(root,pkg)
 c=core.dbopen(db_path)
 if not c.execute('SELECT 1 FROM jobs LIMIT 1').fetchone():register(root,pkg)
 if not execute:return report(c)
 download.check_auth(mode,bucket)   # no EE spending if downloads cannot be authenticated
 ee=eeops.initialize()
 _reconcile(c,ee)
 split=_adaptive_failure_handling(c,pkg)
 got,q=_download_qc(c,root,pkg,mode,bucket)
 incomplete=c.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('INTENT','QUEUED','READY','RUNNING','PENDING','SUBMITTED')").fetchone()[0]
 unaccepted=_unresolved(c)
 cost=report(c)['known_v8_eecu_h']
 # Current-month project baseline must include ALL users and ALL EE products.
 # Avoid double counting historic v8 costs by using maximum of current month project
 # monitoring amount and local estimate, rather than blindly adding them.
 # Use LIVE project-wide Cloud Monitoring (completed + currently processing).
 # The old --month-used-eecu CLI parameter is retained for compatibility but
 # never used as a substitute for the authoritative project metric.
 usage=budget_v9.current_month_eecu_hours(core.PROJECT)
 budget=budget_v9.budget_decision(usage,limit=budget_limit_eecu,simultaneous=max_inflight)
 if not budget['can_submit']:
  return {'status':'BUDGET_FUSE_PAUSE','project_month_live_eecu_h':budget['project_eecu_h'],
   'v8_logged_eecu':cost,'n_running':incomplete,'n_newly_accepted':got,'budget':budget}
 if c.execute("SELECT 1 FROM jobs WHERE family IN ('canary','canary_child') AND state='QUARANTINED' LIMIT 1").fetchone():
  return {'status':'CANARY_SCIENTIFIC_QC_FAILED_GLOBAL_WEATHER_BLOCKED','n_unresolved':unaccepted}
 if c.execute("SELECT COUNT(*) FROM jobs WHERE state='QUARANTINED'").fetchone()[0]>0:
  return {'status':'SCIENTIFIC_TASK_QUARANTINED_PAUSE','hint':'Resolve failed source/geometry/CSV with Codex; cannot publish a silently incomplete global panel'}
 if unaccepted>max_unaccepted:
  return {'status':'INCOMPLETE_FILES_OR_QUARANTINE_PAUSE','n_unresolved':unaccepted,
    'hint':'Investigate missing export files or QC errors before continuing','accepted_this_tick':got}
 slots=max(0,max_inflight-incomplete)
 new=[];errors=[]
 if slots:
  for row in _choose_jobs(c,'any',slots,_legacy_canary(c)):
   try:new.append(_submit(c,ee,root,pkg,row,mode,bucket))
   except Exception as e:
    errors.append({'key':row['key'],'type':type(e).__name__,'error':str(e)[:500]})
    # If before submit intent, quarantine; if after intent, preserve intent.
    st=c.execute('SELECT state FROM jobs WHERE key=?',(row['key'],)).fetchone()[0]
    if st=='PLANNED':core.transition(c,row['key'],'PLANNED','QUARANTINED',error=str(e))
 return {'status':'PRODUCTION_TICK_EXECUTED_NOT_GLOBAL_DONE','submitted':new,'adaptive_child_tasks':split,'errors':errors,
  'accepted_this_tick':got,'quarantined_this_tick':q,'known_v8_eecu_h':cost,
  'live_or_queued':incomplete,'canary_science_equivalence_pass':_legacy_canary(c)}

def run_loop(root,pkg,mode,bucket,max_inflight,max_unaccepted,month_used_eecu,budget_limit_eecu,poll_seconds=90):
 if poll_seconds<15:raise ValueError('No excessive API polling')
 from google.auth.exceptions import TransportError
 from requests.exceptions import RequestException
 transient_failures=0
 while True:
  try:
   z=one_tick(root,pkg,mode,bucket,max_inflight,max_unaccepted,month_used_eecu,budget_limit_eecu,execute=True)
   transient_failures=0
  except (TransportError,RequestException,TimeoutError) as exc:
   transient_failures+=1
   if transient_failures>8:raise
   delay=min(300,15*2**(transient_failures-1))
   print(json.dumps({'status':'TRANSIENT_NETWORK_RETRY_NO_NEW_SUBMISSION',
       'attempt':transient_failures,'retry_after_seconds':delay,
       'error_type':type(exc).__name__}),flush=True)
   time.sleep(delay)
   continue
  except RuntimeError as exc:
   if not str(exc).startswith('Live GEE status unavailable for '):raise
   transient_failures+=1
   if transient_failures>8:raise
   delay=min(300,15*2**(transient_failures-1))
   print(json.dumps({'status':'TRANSIENT_GEE_STATUS_RETRY_NO_NEW_SUBMISSION',
       'attempt':transient_failures,'retry_after_seconds':delay}),flush=True)
   time.sleep(delay)
   continue
  print(json.dumps(z,ensure_ascii=False),flush=True)
  if z['status']!='PRODUCTION_TICK_EXECUTED_NOT_GLOBAL_DONE':break
  c=core.dbopen(pathlib.Path(pkg)/'reports'/'v8_production.sqlite')
  if not c.execute("SELECT 1 FROM jobs WHERE state NOT IN ('ACCEPTED','QUARANTINED','SPLIT') LIMIT 1").fetchone():break
  time.sleep(poll_seconds)
 return z
