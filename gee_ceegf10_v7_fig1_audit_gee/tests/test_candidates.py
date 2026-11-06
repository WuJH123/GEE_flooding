import pandas as pd
import pytest
from cee_v7.candidates import build_candidates,make_plan

def fake_cases():
 return pd.DataFrame([{'case_id':'X','grid_id':'0_0','city_id':'U1','date_utc':'2022-07-20',
                       'pair_id':'pair_X','case_control':'reported_case'}])

def test_unreported_stays_unlabeled():
 d,r=build_candidates(fake_cases(),4)
 assert set(d.case_control)=={'reported_case','unlabeled_calendar_candidate'}
 assert not d.is_verified_no_flood.any()
 assert len(d)==5
 assert r['no_flood_negative_count']==0
 assert all(abs(int(x))>=14 and int(x)%7==0 for x in d.offset_days.iloc[1:])

def test_plan_bounds_and_unique_by_utc_date():
 d,_=build_candidates(fake_cases(),2)
 grid=pd.DataFrame({'grid_id':['0_0'],'grid_x':[0],'grid_y':[0]})
 days,plan=make_plan(d,grid,max_cells=2)
 assert plan.n_grid_days.max()==1
 assert plan.request_key.is_unique
 assert days.duplicated(['grid_id','date_utc']).sum()==0

def test_negative_grid_floor_division():
 c=pd.DataFrame([{'grid_id':'-1_-1','date_utc':'2022-07-20'}]);grid=pd.DataFrame([{'grid_id':'-1_-1','grid_x':-1,'grid_y':-1}])
 d,p=make_plan(c,grid)
 assert p.tile_x0.iloc[0]==-10 and p.tile_y0.iloc[0]==-10

def test_refuse_actual_dry_negative_label():
 cases=fake_cases();cases.loc[0,'case_control']='verified_dry'
 with pytest.raises(ValueError):build_candidates(cases)
