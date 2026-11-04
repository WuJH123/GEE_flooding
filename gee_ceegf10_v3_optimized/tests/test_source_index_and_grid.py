import numpy as np
import rasterio
from rasterio.transform import from_origin
import pytest
from ceeopt.worldcover_local import source_index
from ceeopt.base import load_gf10


def test_worldcover_public_native_epsg4326_source_catalog(tmp_path):
    folder=tmp_path/'raw';folder.mkdir()
    tif=folder/'ESA_WorldCover_10m_2021_v200_N00E000_Map.tif'
    with rasterio.open(tif,'w',driver='GTiff',height=20,width=20,count=1,
               dtype='uint8',crs='EPSG:4326',transform=from_origin(0.0,1.0,0.0001,0.0001),nodata=0) as ds:
        ds.write(np.full((20,20),50,dtype=np.uint8),1)
    result=source_index(folder,tmp_path/'index.json',strict_full=False)
    assert result['files']==1
    import json
    j=json.loads((tmp_path/'index.json').read_text())
    assert len(j['items'][0]['bounds_6933'])==4
    with pytest.raises(ValueError,match='Expected 2651'):
        source_index(folder,tmp_path/'index2.json',strict_full=True)


def test_grid_metadata_validity_without_external_parquet(tmp_path):
    pa=pytest.importorskip('pyarrow')
    import pandas as pd
    f=tmp_path/'grid.parquet'
    pd.DataFrame({'grid_id':['-1_0','0_0'], 'grid_x':[-1,0],
                 'grid_y':[0,0],'land_area_km2':[20.0,55.5]}).to_parquet(f)
    assert len(load_gf10(f,strict=False))==2
    x=pd.DataFrame({'grid_id':['-1_0','-1_0'], 'grid_x':[-1,-1],
                 'grid_y':[0,0],'land_area_km2':[20.0,55.5]})
    x.to_parquet(f)
    with pytest.raises(ValueError,match='Frozen grid_id invalid'):
        load_gf10(f,strict=False)
