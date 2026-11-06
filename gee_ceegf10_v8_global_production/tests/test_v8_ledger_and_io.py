import pathlib,tempfile,sqlite3
import pytest
from cee_v8 import core,download,eeops

def test_source_digest_and_atomic_write():
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'a.json';core.write_json(p,{'x':1});assert core.read_json(p)=={'x':1}
  assert len(core.sha(p))==64
  core.write_json(p,{'x':2});assert core.read_json(p)['x']==2

def test_resumable_ledger_intent_survives_restart():
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'ledger.sqlite';c=core.dbopen(p)
  c.execute("INSERT INTO jobs (key,family,state,source_sha,n_rows,updated) VALUES ('w','weather','PLANNED','x',3,'now')");c.commit()
  core.transition(c,'w','PLANNED','INTENT',task_id=None)
  c.close();c2=core.dbopen(p)
  row=c2.execute("SELECT state,task_id FROM jobs WHERE key='w'").fetchone()
  assert row['state']=='INTENT' and row['task_id'] is None
  c2.close()

def test_merit_does_not_accept_unknown_global_source():
 assert core.PROJECT=='future-shuttle-513705-g9'
 assert core.PERMANENT_END=='2025-09-30'
 assert core.GRID_SHA=='4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d'

def test_local_download_extension_identity_not_accidental_prefix():
 with tempfile.TemporaryDirectory() as t:
  name=core.RUN+'_W8_TEST'
  p=pathlib.Path(t)/(name+'.csv');p.write_text('ok',encoding='utf8')
  assert download.get_source(name,t,'drive',kind='weather')==p

def test_ee_export_enforces_namespace_before_cloud_call():
 with pytest.raises(ValueError,match='namespace'):
  eeops.export(None,'weather',None,'NOT_V8_NAME')

def test_antimeridian_weather_periodic_segments_conserve_width():
 from cee_v8.eeops import projected_seam_segments
 for x in [-1745,-1740,-1737,1736,1740,1750,1100]:
  parts=projected_seam_segments(x,200)
  assert 1<=len(parts)<=2
  assert abs(sum(z[2]-z[0] for z in parts)-10000)<1e-5
  assert all(z[0]<z[2] for z in parts)
