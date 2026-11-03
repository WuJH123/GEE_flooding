"""V2.3 regression: no silent CRS assumptions for arbitrary rasters."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from ceeall.raster import ensure_grip4_georeference


def test_non_grip_products_unchanged(tmp_path):
    assert ensure_grip4_georeference(tmp_path, tmp_path/'any.tif', 'gmted') is None

def test_grip_product_path_is_strict(tmp_path):
    p=tmp_path/'elsewhere'/'grip4_total_dens_m_km2.asc'
    p.parent.mkdir()
    p.write_text('bad file',encoding='utf8')
    with pytest.raises(ValueError, match='restricted to official staged'):
        ensure_grip4_georeference(tmp_path,p,'grip-density')

def test_grip_invalid_grid_rejected_before_projection_write(tmp_path):
    import rasterio
    import numpy as np
    from rasterio.transform import from_origin
    p=tmp_path/'data/staged/cee_all/GRIP4_density_total/grip4_total_dens_m_km2.asc'
    p.parent.mkdir(parents=True)
    with rasterio.open(p,'w',driver='AAIGrid',count=1,width=6,height=3,dtype='float32',
         transform=from_origin(-180,90,60,60),nodata=-9999) as ds:
        ds.write(np.zeros((3,6),dtype=np.float32),1)
    with pytest.raises(ValueError,match='wrong global dimensions'):
        ensure_grip4_georeference(tmp_path,p,'grip-density')
    assert not p.with_suffix('.prj').exists()

def test_shapely_2_2_transform_works_without_deprecation():
    import warnings
    from shapely.geometry import LineString
    from shapely import transform
    from pyproj import Transformer
    tr=Transformer.from_crs(6933,4326,always_xy=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error',DeprecationWarning)
        v=transform(LineString([(0,0),(10000,0)]),tr.transform,interleaved=False)
    assert v.length>0


def test_native_grip_5arcminute_wgs84_prj_readable_and_non_destructive(tmp_path):
    """Full 4320x2160 synthetic AAIGrid tests actual GDAL .prj recognition.

    We do NOT use a miniature source to bypass production extent guards.
    """
    import hashlib
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    p=tmp_path/'data/staged/cee_all/GRIP4_density_total/grip4_total_dens_m_km2.asc'
    p.parent.mkdir(parents=True)
    with rasterio.open(p,'w',driver='AAIGrid',width=4320,height=2160,count=1,
       transform=from_origin(-180,90,1/12,1/12),dtype='int16',nodata=-9999) as ds:
        arr=np.zeros((1,4320),dtype=np.int16)
        for row in range(2160):
            ds.write(arr,1,window=((row,row+1),(0,4320)))
    before=hashlib.sha256(p.read_bytes()).hexdigest()
    initial=ensure_grip4_georeference(tmp_path,p,'grip-density')
    assert initial['metadata_before']['crs'] is None
    assert initial['metadata_after']['crs'] in ('OGC:CRS84','EPSG:4326')
    assert initial['sidecar_created']
    assert p.with_suffix('.prj').exists()
    second=ensure_grip4_georeference(tmp_path,p,'grip-density')
    assert not second['sidecar_created']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before
    with rasterio.open(p) as src:
        assert src.crs.is_geographic
        assert src.read(1,window=((0,1),(0,1)))[0,0]==0
