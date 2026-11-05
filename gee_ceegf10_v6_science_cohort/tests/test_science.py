import pytest,numpy as np
from cee_v6.science import approve,buffered_geometry,BANDS

def test_buffered_core_geometry_and_valid_extent():
    limits=(-17367530.,17367530.,-7340000.,7340000.)
    calc,exp=buffered_geometry([100000,200000,200000,300000],40,limits)
    assert calc==[60000.,160000.,240000.,340000.]
    assert exp==[104999.,204999.,195001.,295001.]
    with pytest.raises(ValueError,match='quarantine'):
        buffered_geometry([-17365000,0,-17355000,10000],20,limits)

def test_halo_not_approved_without_three_regions_and_two_scales(tmp_path):
    key='merit_1090_360_10'
    good=[{'band':s,'n':100,'mask_mismatch':0,'p95_rel':0.,'max_rel':0.} for s in BANDS]
    rows=[{'tile_key':key,'ref_halo_km':20,'probe_halo_km':40,
           'source_tif_sha256':'a','reference_tif_sha256':'b','bands':good}]
    with pytest.raises(ValueError,match='Missing independently'):
        approve(rows,[key],tmp_path/'qc.json')
    rows.append({**rows[0],'ref_halo_km':40,'probe_halo_km':80})
    result=approve(rows,[key],tmp_path/'qc.json')
    assert result['status'].startswith('PASS_')
    rows[1]['bands']=[dict(x, max_rel=.0898) if x['band']=='merit_upa_mean_km2' else x for x in good]
    with pytest.raises(FileExistsError):
        approve(rows,[key],tmp_path/'qc.json')
    result=approve(rows,[key],tmp_path/'fail.json')
    assert result['status']=='FAIL_SCIENTIFIC_EQUIVALENCE'
