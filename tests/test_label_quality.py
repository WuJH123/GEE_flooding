from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform
from gee_flooding.labels import intersect_cells,classify,CELL

def test_projected_cell_overlap():
    back=Transformer.from_crs(6933,4326,always_xy=True)
    fwd=Transformer.from_crs(4326,6933,always_xy=True)
    cell=box(CELL+100,2*CELL+100,CELL+900,2*CELL+900)
    geo=transform(back.transform,cell)
    matched,status=intersect_cells(geo,{'1_2'},fwd)
    assert status=='MATCHED' and matched[0][0]=='1_2'
    assert matched[0][1]>.99
    assert classify(len(matched),matched[0][1])=='HIGH_GEOCODE_SPECIFICITY'

def test_broad_geometry_rejected():
    matched,status=intersect_cells(box(-10,-10,10,10),{'0_0'},
        Transformer.from_crs(4326,6933,always_xy=True))
    assert status=='GEOCODE_TOO_BROAD' and not matched

def test_low_quality_not_promoted():
    assert classify(12,.1)=='LOW_GEOCODE_SPECIFICITY'
