from pathlib import Path
import pytest
from gee_flooding.paths import safe_output
from gee_flooding.grid import _area_ratio

def test_write_path_guard(tmp_path):
    assert safe_output(tmp_path,'outputs/labels/new.parquet').is_relative_to(tmp_path)
    with pytest.raises(ValueError):
        safe_output(tmp_path,'../Global_flooding/forbidden.parquet')

def test_equal_area_projection_sample():
    for x,y in [(0,0),(-500,100),(1200,-500),(-1700,700)]:
        assert abs(_area_ratio(x,y)-1)<0.005
