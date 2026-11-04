"""Real rasterio WarpedVRT, GSHHG L1-L4, COG reproject and per-GF10 parquet.

CI always installs pyarrow; bare artifact build environment may skip only this integration.
"""
import pytest
pa=pytest.importorskip('pyarrow')
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer
from shapely.geometry import box
from shapely import transform as transform_geometry
from ceeopt import worldcover_local as wc


def test_native10m_2d_end_to_end_with_true_land(tmp_path):
    # Global source geometry near (0,0), synthetic category entirely built-up.
    src=tmp_path/'worldcover_2021_test.tif'
    a=np.full((2200,2200),50,dtype=np.uint8)
    with rasterio.open(src,'w',driver='GTiff',width=2200,height=2200,count=1,
           dtype='uint8',nodata=0,crs='EPSG:4326',transform=from_origin(-0.03,0.15,0.00008,0.00008),
           tiled=True,blockxsize=256,blockysize=256,compress='deflate') as f:
        f.write(a,1)
    # GSHHG full land extent equal to exactly one 10km GF10 cell, with small
    # simplification tolerance due to equal-area inverse-project edges.
    to_geo=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True)
    geo=transform_geometry(box(-100,-100,10100,10100),to_geo.transform,interleaved=False)
    files={}
    for level in (1,2,3,4):
        f=tmp_path/f'GSHHS_f_L{level}.shp'
        polygon=geo if level==1 else box(40,40,40.01,40.01)
        gpd.GeoDataFrame({'id':[level]},geometry=[polygon],crs='EPSG:4326').to_file(f)
        files[f'GSHHS_f_L{level}.shp']=f
    index={'items':[{'name':str(src),'bounds_6933':[-5000,-5000,20000,20000]}]}
    out=tmp_path/'out'
    wc._worker_init(index,files,out,10,'test-product-sha','test-gf10-sha')
    result=wc._block_compute((0,0,1,[(0,0,'0_0',100.0)]))
    assert result['status']=='WROTE'
    p=pd.read_parquet(out/'tiles'/'part_0_0_1.parquet')
    assert len(p)==1
    assert p.wc_50_fraction_fullcell.iloc[0]>0.99
    assert p.wc_50_fraction_land.iloc[0]>0.99
    assert p.wc_vegetation_fraction_land.iloc[0]<1e-8
    # Finished shard has immutable QC and is recognized as reusable.
    reused=wc._block_compute((0,0,1,[(0,0,'0_0',100.0)]))
    assert reused['status']=='REUSED'
