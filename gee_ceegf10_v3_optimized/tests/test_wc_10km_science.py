import numpy as np
import pandas as pd
import pytest
from ceeopt.worldcover_local import pixel_summary,block_plan,file_candidates
from ceeopt.base import WC_CLASSES,WC_FIELDS


def test_native_class_full_and_true_land_denominators():
    classes=np.array([[10,10,50,80],[10,50,80,0],[50,50,80,80],[10,50,0,0]],dtype=np.uint8)
    land=np.array([[1,1,0,0],[1,1,0,0],[1,1,0,0],[0,1,0,0]],dtype=np.uint8)
    m=pixel_summary(classes,land)
    assert m['wc_gshhg_land_fraction_raster']==7/16
    assert m['wc_valid_fraction_fullcell']==13/16
    assert m['wc_10_fraction_fullcell']==4/16
    assert m['wc_10_fraction_land']==3/7
    assert m['wc_50_fraction_land']==4/7
    assert abs(sum(m[f'wc_{c}_fraction_land'] for c in WC_CLASSES)-1)<1e-10
    assert abs(sum(m[f'wc_{c}_fraction_fullcell'] for c in WC_CLASSES)-m['wc_valid_fraction_fullcell'])<1e-10
    assert len(WC_FIELDS)==25


def test_unknown_source_class_must_not_be_silently_ignored():
    with pytest.raises(ValueError,match='Unknown WorldCover codes'):
        pixel_summary(np.array([[10,255]],np.uint8),np.ones((1,2),np.uint8))


def test_positive_land_but_zero_rasterized_pixel_has_missing_land_class():
    x=pixel_summary(np.zeros((3,3),np.uint8),np.zeros((3,3),np.uint8))
    assert np.isnan(x['wc_50_fraction_land'])
    assert x['wc_valid_fraction_fullcell']==0


def test_tile_grid_indices_keep_negative_grid_ids():
    g=pd.DataFrame({'grid_id':['-1_0','-10_-11','1097_367'],
         'grid_x':[-1,-10,1097],'grid_y':[0,-11,367],'land_area_km2':[50,50,50]})
    p=block_plan(g,10)
    assert list(zip(p.bx,p.by))==[(-10,0),(-10,-20),(1090,360)]


def test_source_projected_candidates():
    items=[{'bounds_6933':[0,0,1000,1000]},{'bounds_6933':[2000,2000,3000,3000]}]
    assert len(file_candidates(items,[10,10,500,500]))==1
