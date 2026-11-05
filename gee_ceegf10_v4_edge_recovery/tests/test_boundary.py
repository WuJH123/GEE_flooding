import numpy as np
import pandas as pd
import pytest
from cee_recover.geometry import crop_tile,validate_raster_metadata,valid_limits

def data(xy):
    return pd.DataFrame([{'grid_id':f'{x}_{y}','grid_x':x,'grid_y':y,'land_area_km2':30.0} for x,y in xy])

def test_failed_nominal_west_tile_crops_to_only_real_land():
    p=crop_tile(data([(-1736,-239),(-1735,-238),(-1735,-239)]),-1740,-240,10)
    assert p.original_key=='merit_-1740_-240_10'
    assert p.status=='SAFE_COMPACT'
    assert (p.x_min,p.y_min,p.width,p.height)==(-1736,-239,2,2)
    assert p.work_bounds()==[-17360000,-2390000,-17340000,-2370000]
    assert p.width*p.height==4 and p.n_land==3
    assert p.export_bounds()==[-17355001,-2385001,-17344999,-2374999]

def test_projection_seam_quarantine_outside_valid_world():
    p=crop_tile(data([(-1737,-239),(-1736,-239)]),-1740,-240,10)
    assert p.status=='QUARANTINE_SEAM'

def test_expected_wuhan_10x10_unmodified():
    p=crop_tile(data([(x,y) for x in range(1097,1107) for y in range(367,377)]),1097,367,10)
    assert (p.status,p.width,p.height,p.n_land)==('SAFE_COMPACT',10,10,100)
    assert p.expected_transform()==[10000,0,10970000,0,-10000,3770000]

def test_absurd_width_3474_rejected_even_if_ee_succeeded():
    p=crop_tile(data([(-1736,-239),(-1735,-238)]),-1740,-240,10)
    correct={'crs':6933,'width':2,'height':2,'count':16,'transform':p.expected_transform()}
    assert validate_raster_metadata(correct,p)
    with pytest.raises(ValueError,match='Invalid GEE exported shape'):
        validate_raster_metadata({**correct,'width':3474,'height':10},p)

def test_extra_border_column_and_wrong_shift_rejected():
    p=crop_tile(data([(x,y) for x in range(1097,1107) for y in range(367,377)]),1097,367,10)
    good={'crs':6933,'width':10,'height':10,'count':16,'transform':p.expected_transform()}
    with pytest.raises(ValueError):validate_raster_metadata({**good,'width':11},p)
    with pytest.raises(ValueError):validate_raster_metadata({**good,'transform':[10000,0,10975000,0,-10000,3770000]},p)

def test_valid_world_limit_from_crs_not_arbitrary_lon_degree():
    left,right,bottom,top=valid_limits()
    assert left < -17360000 and left > -17400000
    assert right > 17360000 and right < 17400000
    assert bottom < -7300000 and top > 7300000

def test_empty_land_block_skips():
    assert crop_tile(data([(0,0)]),1000,2000,10).status=='SKIP_EMPTY'
