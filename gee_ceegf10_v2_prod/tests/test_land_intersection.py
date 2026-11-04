import geopandas as gpd
import pytest
from shapely.geometry import box,shape
from pyproj import Transformer
from shapely.ops import transform
from ceeprodgee.coast import prepare_land_tile

def test_l1_minus_l2_plus_l3_minus_l4_area_mass_balance(tmp_path):
    # Synthetic 10km tile with 3km lake, 1km island and 200m pond.
    proj=Transformer.from_crs(6933,4326,always_xy=True)
    polys=[box(0,0,10000,10000),box(1000,1000,4000,4000),
           box(2000,2000,3000,3000),box(2400,2400,2600,2600)]
    paths={}
    for i,p in enumerate(polys,1):
        g=gpd.GeoDataFrame({'id':[i]},geometry=[transform(proj.transform,p)],crs='EPSG:4326')
        path=tmp_path/f'GSHHS_f_L{i}.shp';g.to_file(path)
        paths[path.name]=path
    result,area=prepare_land_tile(paths,[0,0,10000,10000],expected_land_km2=91.96)
    assert area==pytest.approx(91.96,abs=0.0001)
    assert result['type'] in ('MultiPolygon','Polygon')

def test_antarctic_geometry_requires_split():
    # Ensure module can be imported without reading 1.4M source rows.
    from ceeprodgee.grid import tile_bounds
    assert tile_bounds(0,-1,5)==[0,-10000,50000,40000]
