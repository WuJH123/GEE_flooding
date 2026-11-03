"""End-to-end native-data extraction. Skipped locally if binary wheels unavailable.

On the 96-core Windows server preflight imports required wheels first, so these
must EXECUTE, not silently skip. Test source is synthetic but actual C++ engine.
"""
import pytest
pyarrow=pytest.importorskip('pyarrow')
exactextract=pytest.importorskip('exactextract')
import pandas as pd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from ceeall.raster import _one
from ceeall.common import ensure_job

def test_native_worldclim_exact_small_cell(tmp_path):
    root=tmp_path;src=root/'wc2.1_30s_prec_01.tif'
    # Original-CRS layer covers GF10 origin around equator.
    with rasterio.open(src,'w',driver='GTiff',width=20,height=20,count=1,
      crs='EPSG:4326',transform=from_origin(-0.05,0.10,0.01,0.01),dtype='float32',nodata=-9999) as ds:
      ds.write(np.full((20,20),50,dtype='float32'),1)
    tile=root/'tile_0_0.parquet'
    pd.DataFrame({'grid_id':['0_0'],'grid_x':[0],'grid_y':[0],'land_area_km2':[100.]}).to_parquet(tile,index=False)
    out=root/'native';j=ensure_job(out,{'test':'constant_precip_50'})
    v=_one((str(tile),str(src),'worldclim-monthly',str(out),j))
    assert v[0]=='WROTE'
    q=pd.read_parquet(out/'tiles'/tile.name)
    assert q['wc2_1_30s_prec_01_mean_native'].iloc[0]==pytest.approx(50.,abs=0.05)
    assert _one((str(tile),str(src),'worldclim-monthly',str(out),j))[0]=='REUSED'
