import numpy as np
import pytest
from ceeprodgee.worldcover_local import _overlap,aggregate_categories
from ceeprodgee.worldcover_local_plan import FOUR
from ceeprodgee.worldcover_derived import COMPOSITES

def test_tile_source_intersection_uses_common_projection():
    assert _overlap([0,0,100,100],[50,50,150,150])
    assert not _overlap([0,0,100,100],[100,0,200,100])

def test_four_block_reference_coordinates_frozen():
    assert FOUR['wuhan']==(1097,367)
    assert FOUR['mumbai']==(697,233)
    assert FOUR['iceland']==(-166,658)
    assert FOUR['niger_delta']==(57,52)
    assert len(FOUR)*4==16

def test_source_nodata_land_denominator_not_replaced_by_zero():
    src=np.zeros((2,2),dtype=np.uint8)
    land=np.array([[1,0],[0,0]],dtype=np.uint8)
    x=aggregate_categories(src,land,px_per_cell=2)
    assert x[11,0,0]==0
    assert x[24,0,0]==.25
    assert x[23,0,0]==0 # land exists but ESA coverage zero; source missing, not flood outcome zero
    # A true missingness flag must travel with all downstream ratios.
    assert 'wc_valid_fraction_land' in __import__('ceeprodgee.contract',fromlist=['WC_BANDS']).WC_BANDS

def test_missing_esa_categorical_coverage_is_nan_not_false_zero():
    src=np.zeros((2,2),dtype=np.uint8)
    land=np.ones((2,2),dtype=np.uint8)
    b=aggregate_categories(src,land,2)
    assert b[11,0,0]==0
    assert np.isnan(b[:11,0,0]).all()
    assert np.isnan(b[12:23,0,0]).all()
    assert b[23,0,0]==0
