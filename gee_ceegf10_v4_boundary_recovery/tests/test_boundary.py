from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest
from cee_boundary_v4.core import Tile,projected_mode,pixel_centers_region,validate_frozen_subset,X_LIMIT,Y_LIMIT
from cee_boundary_v4.audit import audit_boundary_csv

BANDS=('merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2','merit_permanent_water_fraction',
'merit_valid_fraction','merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
'merit_hand_le10_fraction_valid','merit_slope_mean_deg','merit_slope_le2_fraction_valid',
'merit_upa_max_km2','merit_upa_max_log1p','merit_hand_p10_m',
'merit_hand_p50_m','merit_hand_p90_m','merit_upa_p90_km2')

def test_epsg6933_west_boundary_detected_before_gee():
    assert 17_300_000<X_LIMIT<17_400_000
    assert projected_mode(Tile(-1740,-240,10))=='POINT_TABLE'
    with pytest.raises(ValueError):pixel_centers_region(Tile(-1740,-240,10))
    assert projected_mode(Tile(1097,367,10))=='FIXED_RASTER'
    assert pixel_centers_region(Tile(1097,367,10))==(10975000.,3675000.,11065000.,3765000.)

def test_point_expected_id_on_partial_3land_cell_block():
    g=pd.DataFrame([ (f'{x}_{-237}',x,-237,50.0) for x in (-1736,-1735)],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    tile=Tile(-1740,-240,10)
    assert len(validate_frozen_subset(g,tile))==2
    assert tile.point(-1736,-237)==(-17355000,-2365000)


def test_boundary_table_schema_16bands_and_duplicate_rejection(tmp_path):
    tile=Tile(-1740,-240,10)
    g=pd.DataFrame([('-1736_-237',-1736,-237,10.0),('-1735_-237',-1735,-237,20.0)],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    df=g[['grid_id','grid_x','grid_y']].copy()
    for b in BANDS:df[b]=0.0
    df['merit_valid_fraction']=1.0
    p=tmp_path/'result.csv';df.to_csv(p,index=False)
    out=audit_boundary_csv(p,g,tile,BANDS)
    assert out['n_rows']==2 and out['n_hand_valid']==2
    df.loc[1,'grid_id']='-1736_-237';df.to_csv(p,index=False)
    with pytest.raises(ValueError,match='duplicate'):
        audit_boundary_csv(p,g,tile,BANDS)

def test_no_fabricated_missing_era5_from_unverified_news_dates(tmp_path):
    from cee_boundary_v4.cohort import audit
    p=tmp_path/'news.csv';pd.DataFrame({'grid_id':['1_1'],'date_utc':['2023-01-01']}).to_csv(p,index=False)
    with pytest.raises(ValueError,match='independently matched'):
        audit(p,{'1_1'},tmp_path/'qc.json')

def test_matched_unlabeled_case_control_accepted_with_warning(tmp_path):
    from cee_boundary_v4.cohort import audit
    p=tmp_path/'cohort.csv'
    d=pd.DataFrame({'grid_id':['1_1','1_1'],'date_utc':['2023-06-01','2023-06-15'],
       'match_set_id':['m1','m1'],'case_control':['case','unlabeled_control'],
       'source_family':['groundsource','matched_unlabeled'],'sampling_rule':['report','same_month'],
       'city_id':['city_A','city_A']})
    d.to_csv(p,index=False)
    a=audit(p,{'1_1'},tmp_path/'qc.json')
    assert a['n_match_sets']==1 and 'NOT_CAUSAL_PROOF' in a['status']

def test_existing_rejected_export_never_counts_as_completed():
    from cee_boundary_v4.core import template_report
    import json,tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'ledger.json'
        path.write_text(json.dumps([{'key':'merit_-1740_-240_10','state':'SUCCEEDED','local_qc_pass':False,'eecu_hours':.00158},
             {'key':'merit_1097_367_10','state':'SUCCEEDED','local_qc_pass':True}]))
        q=template_report(path)
        assert q['invalid']==['merit_-1740_-240_10']


def test_edge_table_strict_missing_expected_id_rejected(tmp_path):
    tile=Tile(-1740,-240,10)
    g=pd.DataFrame([('-1736_-237',-1736,-237,10.0),('-1735_-237',-1735,-237,20.0)],columns=['grid_id','grid_x','grid_y','land_area_km2'])
    x=g.iloc[:1][['grid_id','grid_x','grid_y']].copy()
    for b in BANDS:x[b]=0.0
    p=tmp_path/'partial.csv';x.to_csv(p,index=False)
    with pytest.raises(ValueError,match='membership mismatch'):
        audit_boundary_csv(p,g,tile,BANDS)
