import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from cee_v8.optimizer import pack_safe,split_packed_parent,choose_factor_from_live
import pytest

def fixture(n=4):
 rows=[]
 for x in range(n):
  for y in range(n):
   a=x*10;b=y*10
   ids=[f'{i}_{j}' for i in range(a,a+10) for j in range(b,b+10)]
   rows.append(dict(tile_key=f'merit_{a}_{b}_10',crop_x0=a,crop_y0=b,width=10,height=10,n_land_cells=100,land_ids=';'.join(ids)))
 return rows

def test_reduction_and_preservation():
 o=fixture();p,m=pack_safe(o,4)
 assert len(p)==1 and m['n_original_parent_jobs']==16
 assert p[0]['width']==40 and p[0]['height']==40 and p[0]['n_land_cells']==1600
 assert p[0]['native_source_megapixels_estimate']<42
 assert m['has_independent_live_science_approval'] is False

def test_automatic_bisect_loses_none():
 o=fixture();p,_=pack_safe(o,4);a,b=split_packed_parent(p[0],o)
 assert not set(a['land_ids'].split(';'))&set(b['land_ids'].split(';'))
 assert len(a['land_ids'].split(';'))+len(b['land_ids'].split(';'))==1600

def test_sparse_coastal_doesnt_pack_giant_ocean():
 x=fixture(4)
 for z in x:z['n_land_cells']=1;z['land_ids']=z['land_ids'].split(';')[0]
 p,_=pack_safe(x,4)
 assert len(p)==16

def test_full_duplicates_fatal():
 x=fixture(2);x.append(x[0])
 with pytest.raises(ValueError,match='Duplicate'):pack_safe(x,4)

def test_science_gate_rejects_missing_or_fake():
 assert choose_factor_from_live([dict(factor=4,state='ACCEPTED')]*3)==0

def test_science_gate_passes_three_independent_strata():
 r=[]
 for typ in ['coastal','high_latitude','inland']:
  r.append(dict(factor=2,state='ACCEPTED',source_sha256='a'*64,reference_sha256='b'*64,
       task_id=typ,eecu_h=0.1,reference_count=40,stratum=typ,p95_rel=0.,max_rel=0.,
       mask_mismatch=0,n_bad_bands=0,task_wall_seconds=50))
 assert choose_factor_from_live(r)==2
 r[1]['mask_mismatch']=1
 assert choose_factor_from_live(r)==0
 r[1]['mask_mismatch']=0
 r[1]['state']='SUCCEEDED'
 assert choose_factor_from_live(r)==0
