import tempfile,pathlib,sqlite3
import pandas as pd
import numpy as np
import pytest
from cee_v8 import core,plan,qc,runner

def test_run_loop_retries_transient_oauth_failure_without_a_second_submission(monkeypatch):
 from google.auth.exceptions import TransportError
 calls=[];delays=[]
 def tick(*args,**kwargs):
  calls.append(kwargs)
  if len(calls)==1:raise TransportError('temporary proxy disconnect')
  return {'status':'BUDGET_FUSE_PAUSE'}
 monkeypatch.setattr(runner,'one_tick',tick)
 monkeypatch.setattr(runner.time,'sleep',lambda seconds:delays.append(seconds))
 assert runner.run_loop('root','pkg','drive',None,2,10,0,900,60)=={'status':'BUDGET_FUSE_PAUSE'}
 assert len(calls)==2 and all(z['execute'] for z in calls)
 assert delays==[15]

def test_run_loop_does_not_retry_scientific_error(monkeypatch):
 def tick(*args,**kwargs):raise ValueError('scientific QC changed')
 monkeypatch.setattr(runner,'one_tick',tick)
 with pytest.raises(ValueError,match='scientific QC'):
  runner.run_loop('root','pkg','drive',None,2,10,0,900,60)

def fake(n=30):
 t=pd.date_range('2021-01-01',periods=9)
 return pd.DataFrame({'grid_id':[str(i//3)+'_'+str(i) for i in range(n)],
 'date_utc':[t[i%len(t)].strftime('%Y-%m-%d') for i in range(n)],
 'grid_x':list(range(n)),'grid_y':[3]*n,
 'analysis_role':['SOURCE_REPORT']*n})

def test_macro_group_no_duplicate_and_exact_conservation():
 f=fake(120);a,b=plan.batch_rows(f,max_rows=14,max_days=4)
 assert len(a)==120 and not a.duplicated(['grid_id','date_utc']).any()
 assert a.batch_id.notna().all() and (b.n_rows<=14).all() and (b.days<=4).all()
 assert int(b.n_rows.sum())==len(a)

def test_macro_group_deterministic():
 f=fake(120);a,_=plan.batch_rows(f,max_rows=23,max_days=4)
 g,_=plan.batch_rows(f.sample(frac=1,random_state=10),max_rows=23,max_days=4)
 assert dict(zip(a.grid_id,a.batch_id))==dict(zip(g.grid_id,g.batch_id))

def test_duplicate_keys_rejected():
 f=fake(20)
 with pytest.raises(ValueError,match='Duplicate'):plan.batch_rows(pd.concat([f,f.iloc[:1]]))

def test_macro_oversized_rejected():
 with pytest.raises(ValueError):plan.batch_rows(fake(),max_rows=601)
 with pytest.raises(ValueError):plan.batch_rows(fake(),max_days=9)

def test_adaptive_bisect_disjoint_and_conserves():
 a,b=plan.split_weather_frame(fake(19))
 assert len(a)+len(b)==19
 assert not (set(a.grid_id+'@'+a.date_utc)&set(b.grid_id+'@'+b.date_utc))

def test_adaptive_single_rejected():
 with pytest.raises(ValueError):plan.split_weather_frame(fake(1))

def test_sqlite_idempotent_unique_intents():
 with tempfile.TemporaryDirectory() as t:
  c=core.dbopen(pathlib.Path(t)/'ledger.sqlite')
  c.execute("INSERT INTO jobs(key,family,state,source_sha,n_rows,updated) VALUES('m1','merit','PLANNED','abc',100,'now')")
  c.commit();core.transition(c,'m1','PLANNED','INTENT',task_id='eefake')
  with pytest.raises(ValueError):core.transition(c,'m1','PLANNED','QUEUED')
  assert c.execute("SELECT task_id FROM jobs WHERE key='m1'").fetchone()[0]=='eefake'
  c.close()

def test_report_not_false_seam_completion():
 with tempfile.TemporaryDirectory() as t:
  c=core.dbopen(pathlib.Path(t)/'ledger.sqlite');z=runner.report(c)
  assert z['global_merit_all_GF10_complete'] is False
  assert z['merit_seam450_status'].startswith('QUARANTINED')
  c.close()

def test_weather_accepted_numeric_and_mask_policy():
 f=pd.DataFrame([{'grid_id':'101_22','date_utc':'2021-03-02',
   **{k:0.0 for k in core.FIELDS[2:]}}])
 for k,n in {'imerg_n_obs_day':48,'imerg_n_obs_pre7d':336,'imerg_n_obs_pre14d':672,'imerg_n_obs_pre30d':1440}.items():f[k]=n
 f.loc[0,'era5_soil_l1_prevday_m3m3']=.3;f.loc[0,'era5_soil_l2_prevday_m3m3']=.35
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'one.csv';f.to_csv(p,index=False)
  q=qc.weather(p,f[['grid_id','date_utc']]);assert q['n_grid_dates']==1
  assert q['source_dates_not_independently_verified']

def test_no_incomplete_imerg_pass():
 f=pd.DataFrame([{'grid_id':'1_1','date_utc':'2021-02-01',**{k:0 for k in core.FIELDS[2:]}}]);f.imerg_n_obs_day=47
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'bad.csv';f.to_csv(p,index=False)
  with pytest.raises(ValueError,match='IMERG'):qc.weather(p,f[['grid_id','date_utc']])

def test_weather_canary_numeric_mismatch_blocks_release():
 f=pd.DataFrame([{'grid_id':'1_1','date_utc':'2021-02-01',**{k:0 for k in core.FIELDS[2:]}}]);
 for k,n in {'imerg_n_obs_day':48,'imerg_n_obs_pre7d':336,'imerg_n_obs_pre14d':672,'imerg_n_obs_pre30d':1440}.items():f[k]=n
 b=f.copy();b['imerg_day_mm']=100.0
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'canary.csv';f.to_csv(p,index=False)
  with pytest.raises(ValueError,match='numerical mismatch'):qc.weather(p,f[['grid_id','date_utc']],reference=b)

def test_band_contract_frozen():
 assert len(core.BANDS)==16 and len(core.FIELDS)==20
 assert 'imerg_pre30d_mm' in core.FIELDS
 assert core.GRID_ROWS==1395471
 assert core.RUN.startswith('CEE_GF10_GLOBAL_EE_V8_')

def test_invalid_source_eecu_precheck():
 with pytest.raises(ValueError,match="CURRENT"):
  runner.one_tick('any','/tmp/nonexistent','drive',None,execute=True,budget_used_eecu=None)

def test_merit_coastal_rectangle_checks_only_frozen_land_membership():
 """A 2x2 EE crop contains two finite ocean pixels: only land IDs count."""
 import rasterio
 from affine import Affine
 with tempfile.TemporaryDirectory() as t:
  path=pathlib.Path(t)/'coastal.tif'
  image=np.ones((16,2,2),dtype='float32')
  # One may have available ocean-side values because MERIT valid fraction is 0.
  image[4,0,:]=0.0
  row=pd.Series({'crop_x0':0,'crop_y0':0,'width':2,'height':2,
                 'n_land_cells':2,'land_ids':'0_0;1_0'})
  with rasterio.open(path,'w',driver='GTiff',width=2,height=2,count=16,dtype='float32',
                     crs='EPSG:6933',transform=Affine(10000,0,0,0,-10000,20000),
                     nodata=-9999) as dst:dst.write(image)
  z=qc.merit(path,row)
  assert z['n_GHSHG_land_cells_verified']==2
  assert z['n_pixels']==4
  # The lower left is an expected land cell, so a completely absent source
  # is a hard QC failure even though the *other* pixels have valid numbers.
  image[:,1,0]=-9999
  with rasterio.open(path,'w',driver='GTiff',width=2,height=2,count=16,dtype='float32',
                     crs='EPSG:6933',transform=Affine(10000,0,0,0,-10000,20000),
                     nodata=-9999) as dst:dst.write(image)
  with pytest.raises(ValueError,match='land cell has no source values'):
   qc.merit(path,row)
