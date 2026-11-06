"""Frozen CEE GF10 V8 source contract and durable IO. No cloud side effects."""
from __future__ import annotations
import datetime as dt,hashlib,json,os,pathlib,tempfile,sqlite3
PROJECT='future-shuttle-513705-g9'
RUN='CEE_GF10_GLOBAL_EE_V8_20261106'
GRID_SHA='4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d'
GRID_ROWS=1_395_471
EXPECTED_CASE_DAYS=196_496
PERMANENT_END='2025-09-30'
FIELDS=['grid_id','date_utc','imerg_day_mm','imerg_peak_30min_mm_h',
'imerg_rolling3h_max_mm','imerg_pre7d_mm','imerg_pre14d_mm','imerg_pre30d_mm',
'imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre14d','imerg_n_obs_pre30d',
'era5_soil_l1_prevday_m3m3','era5_soil_l2_prevday_m3m3',
'era5_t2m_prevday_C','era5_rain_prevday_mm','era5_runoff_prevday_mm',
'era5_u_prevday_ms','era5_v_prevday_ms','era5_wind_prevday_ms']
BANDS=['merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2',
'merit_permanent_water_fraction','merit_valid_fraction',
'merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
'merit_hand_le10_fraction_valid','merit_slope_mean_deg',
'merit_slope_le2_fraction_valid','merit_upa_max_km2',
'merit_upa_max_log1p','merit_hand_p10_m','merit_hand_p50_m',
'merit_hand_p90_m','merit_upa_p90_km2']

def root_files(root):
 r=pathlib.Path(root)
 return {'grid':r/'gee_ceegf10_v1'/'gf10_global_nonantarctic_land.parquet',
 'v3':r/'CEE_GF10_EFFICIENT_V3_20261105',
 'v4':r/'CEE_GF10_GEE_RECOVERY_V4_20261105',
 'v6':r/'CEE_GF10_V6_SCIENCE_COHORT_20261105',
 'v7':r/'CEE_GF10_FIG1_AUDIT_GEE_V7_20261106'}

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()

def hashkey(*parts):return hashlib.sha256('|'.join(str(x) for x in parts).encode()).hexdigest()[:20]
def read_json(path,default=None):
 p=pathlib.Path(path)
 return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else default

def write_json(path,x):
 p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=p.name+'.tmp-')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump(x,f,indent=2,ensure_ascii=False,sort_keys=True,default=str);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def validate_grid(path):
 import pandas as pd
 from pyarrow import parquet as pq
 p=pathlib.Path(path)
 if not p.exists():raise FileNotFoundError(p)
 if sha(p)!=GRID_SHA:raise ValueError('FROZEN_GF10_SHA_MISMATCH')
 if pq.ParquetFile(p).metadata.num_rows!=GRID_ROWS:raise ValueError('GF10 count != 1395471')
 f=pd.read_parquet(p,columns=['grid_id','grid_x','grid_y','land_area_km2'])
 if f.grid_id.duplicated().any() or f[['grid_x','grid_y']].duplicated().any():raise ValueError('GF10 duplicate keys')
 if not f.land_area_km2.between(0,100.0001,inclusive='right').all():raise ValueError('Invalid land area')
 return f

def validate_science(files):
 g=read_json(files['v6']/'reports'/'merit_halo_science_gate_v6.json')
 if not g or g.get('status')!='PASS_20_40_80_HALO_NUMERIC_CONVERGENCE':raise ValueError('V6 MERIT scientific convergence gate not passed')
 if int(g.get('source_gf10_n',0))!=GRID_ROWS:raise ValueError('MERIT gate wrong GF10')
 return g

DB_SCHEMA='''CREATE TABLE IF NOT EXISTS jobs (
 key TEXT PRIMARY KEY, family TEXT NOT NULL, state TEXT NOT NULL,
 parent TEXT, operation TEXT, task_id TEXT, file_name TEXT,
 source_sha TEXT NOT NULL, description TEXT, n_rows INTEGER NOT NULL,
 tries INTEGER NOT NULL DEFAULT 0, depth INTEGER NOT NULL DEFAULT 0,
 eecu_h REAL, local_sha TEXT, error TEXT, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs(state,family);
CREATE TABLE IF NOT EXISTS revisions (ts TEXT, job_key TEXT, old_state TEXT, new_state TEXT, details TEXT);
'''

def dbopen(path):
 p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(p,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=30000');c.executescript(DB_SCHEMA)
 return c

def timestamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def transition(c,key,old,new,**kw):
 row=c.execute('SELECT * FROM jobs WHERE key=?',(key,)).fetchone()
 if row is None or row['state']!=old:raise ValueError(f'Illegal task transition {key}: expected={old} actual={row["state"] if row else "MISSING"}')
 parts=['state=?','updated=?'];args=[new,timestamp()]
 allowed={'operation','task_id','file_name','eecu_h','local_sha','error','tries','depth','parent'}
 for k,v in kw.items():
  if k not in allowed:raise KeyError(k)
  parts.append(k+'=?');args.append(v)
 c.execute('UPDATE jobs SET '+','.join(parts)+' WHERE key=?',(*args,key))
 c.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(timestamp(),key,old,new,json.dumps(kw,default=str)))
 c.commit()

def accepted_keys(c,family):return {r[0] for r in c.execute('SELECT key FROM jobs WHERE family=? AND state="ACCEPTED"',(family,))}
