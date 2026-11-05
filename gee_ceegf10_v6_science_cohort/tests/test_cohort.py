import pandas as pd,numpy as np,pytest
from cee_v6.cohort import generate_calendar_candidates,make_request_plan,freeze_cases,REQUIRED


def _cases():
    return pd.DataFrame([{'case_id':'a1','grid_id':'10_20','date_utc':'2022-06-01','city_id':'C1','case_control':'reported_case'},
                         {'case_id':'a2','grid_id':'20_30','date_utc':'2022-07-20','city_id':'C2','case_control':'reported_case'}])

def test_unreported_is_not_real_no_flood():
    c=_cases();frame,q=generate_calendar_candidates(c,n_candidates=4)
    assert q['n_reported_cases']==2
    assert q['not_true_flood_negatives']
    assert q['storm_catalog_verified'] is False
    assert 'confirmed_no_flood' not in set(frame.case_control)
    assert set(frame.case_control)=={'reported_case','unlabeled_calendar_candidate'}
    assert (frame[frame.case_control=='unlabeled_calendar_candidate'].offset_days.abs()>=14).all()
    assert frame.pair_id.nunique()==2

def test_weather_requests_unique_dates_and_floor_negative_xy():
    c,_=generate_calendar_candidates(_cases(),2)
    g=pd.DataFrame({'grid_id':['10_20','20_30'],'grid_x':[10,20],'grid_y':[20,30]})
    d,p=make_request_plan(c,g)
    assert len(d)==len(c[['grid_id','date_utc']].drop_duplicates())
    assert p.n_grid_days.max()<=100
    assert p.request_key.is_unique

def test_case_precision_is_a_hard_gate(tmp_path):
    pytest.importorskip("pyarrow")
    source=tmp_path/'fig1.csv';grid=tmp_path/'grid.parquet'
    pd.DataFrame({'evt':['ev1','ev2'],'grid':['10_20','10_20'],
      'day':['2022-06-01','2022-06-02'],'city':['C1','C1'],
      'origin':['Groundsource','Groundsource'],'when':['exact_day','month'],
      'where':['street','country']}).to_csv(source,index=False)
    pd.DataFrame({'grid_id':['10_20'],'grid_x':[10],'grid_y':[20],
                  'land_area_km2':[90.]}).to_parquet(grid,index=False)
    mapping=dict(zip(REQUIRED,['evt','grid','day','city','origin','when','where']))
    out,r=freeze_cases(source,mapping,grid,tmp_path/'out',strict_grid=False)
    assert len(out)==1
    assert r['excluded_time_precision']==1
    assert r['excluded_location_precision']==1
    assert r['n_source_records']==2
    assert out.storm_id.isna().all()


def test_bad_grid_or_mapping_cannot_be_silently_fixed(tmp_path):
    pytest.importorskip("pyarrow")
    g=tmp_path/'g.parquet'
    pd.DataFrame({'grid_id':['4_5'],'grid_x':[4],'grid_y':[5],'land_area_km2':[1.]}).to_parquet(g)
    f=tmp_path/'x.csv'
    pd.DataFrame({'event':['1'],'cell':['4_5'],'date':['2022-07-01'],
                  'city':['C'],'src':['news'],'t':['exact_day'],'loc':['street']}).to_csv(f,index=False)
    mapping=dict(zip(REQUIRED,['event','cell','date','city','src','t','loc']))
    with pytest.raises(ValueError,match='GF10 SHA'):
        freeze_cases(f,mapping,g,tmp_path/'out')
    with pytest.raises(ValueError,match='Mapping'):
        freeze_cases(f,{'grid_id':'cell'},g,tmp_path/'out',strict_grid=False)
