import pytest
pyarrow=pytest.importorskip('pyarrow')
exactextract=pytest.importorskip('exactextract')
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from ceeall.gisd import _source_one
from ceeall.common import ensure_job

def test_gisd_source_overlap_and_classes(tmp_path):
    src=tmp_path/'GISD30_1985-2020_E0N0.tif'
    with rasterio.open(src,'w',driver='GTiff',width=20,height=20,count=1,
         crs='EPSG:4326',transform=from_origin(-0.05,0.15,0.01,0.01),dtype='uint8',nodata=255) as f:
         f.write(np.full((20,20),4,dtype='uint8'),1)
    gf=tmp_path/'grid.parquet'
    pd.DataFrame({'grid_id':['0_0'],'grid_x':[0],'grid_y':[0]}).to_parquet(gf,index=False)
    out=tmp_path/'output';jid=ensure_job(out,{'test':'synthetic_GISD30'})
    result=_source_one((str(src),str(gf),str(out),jid))
    assert result['status']=='WROTE'
    d=pd.read_parquet(out/(src.stem+'.parquet'))
    assert len(d)==1
    assert d['impervious_2000_count'].iloc[0]>0
    assert d['impervious_2020_count'].iloc[0]>0
