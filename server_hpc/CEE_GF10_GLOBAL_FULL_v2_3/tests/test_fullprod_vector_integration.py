from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString,box
import numpy as np
import pandas as pd
import pytest


def _source(tmp_path,typ):
    root=tmp_path/'data/staged/cee_all'
    root.mkdir(parents=True,exist_ok=True)
    if typ=='roads':
        p=root/'GRIP4_global_vector_fgdb.gpkg'
        gdf=gpd.GeoDataFrame({'road_id':['1']},geometry=[LineString([(0,5000),(18000,5000)])],crs='EPSG:6933')
    else:
        p=root/'geoBoundariesCGAZ_ADM0.gpkg'
        gdf=gpd.GeoDataFrame({'shapeGroup':['AAA']},geometry=[box(0,0,10000,10000)],crs='EPSG:6933')
    gdf.to_file(p,driver='GPKG')
    return p


def test_automatic_provider_layer_detection(tmp_path):
    from ceeprod.discover import discover_family
    _source(tmp_path,'roads');_source(tmp_path,'admin0')
    r=discover_family(tmp_path,'roads')
    assert r.id_field=='road_id'
    assert 'line' in r.geometry_type.lower()
    a=discover_family(tmp_path,'admin0')
    assert a.id_field=='shapeGroup'


def test_exact_geodesic_network_clips_all_cells(tmp_path):
    pytest.importorskip('pyarrow')
    from ceeprod.discover import discover_family
    from ceeprod.vector_full import _overlay_source
    from dataclasses import asdict
    _source(tmp_path,'roads')
    cells=tmp_path/'tile_0_0.parquet'
    pd.DataFrame({'grid_id':['0_0','1_0'],'grid_x':[0,1], 'grid_y':[0,0],
                  'land_area_km2':[100.,100.]}).to_parquet(cells,index=False)
    out=tmp_path/'work'
    r=_overlay_source((asdict(discover_family(tmp_path,'roads')),str(cells),str(out),'job1'))
    assert r['n_grid']==2 and r['n_matched']==2
    d=pd.read_parquet(out/'tiles'/cells.name)
    assert (d.roads_length_km_geodesic>0).all()
    assert d.roads_length_km_geodesic.iloc[0]>d.roads_length_km_geodesic.iloc[1]


def test_polygon_country_intersection_not_pseudo_5000(tmp_path):
    pytest.importorskip('pyarrow')
    from ceeprod.discover import discover_family
    from ceeprod.vector_full import _overlay_source
    from dataclasses import asdict
    _source(tmp_path,'admin0')
    cells=tmp_path/'tile_0_0.parquet'
    pd.DataFrame({'grid_id':['0_0','1_0'],'grid_x':[0,1],'grid_y':[0,0],
                  'land_area_km2':[100.,100.]}).to_parquet(cells,index=False)
    out=tmp_path/'work'
    _overlay_source((asdict(discover_family(tmp_path,'admin0')),str(cells),str(out),'job1'))
    d=pd.read_parquet(out/'tiles'/cells.name)
    assert d.admin0_dominant_native_id.iloc[0]=='AAA'
    assert d.admin0_dominant_intersection_km2.iloc[0]==pytest.approx(100)
    assert d.admin0_dominant_intersection_km2.iloc[1]==0
