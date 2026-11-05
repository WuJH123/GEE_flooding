import numpy as np
import rasterio
from rasterio.transform import from_origin
from ceeprodgee.worldcover_local import rasterise_source,aggregate_categories,write_tile
from ceeprodgee.qc import check_raster

def test_one_pass_source_warp_and_25band_gf10_qc(tmp_path):
    # Tiny artificial EPSG6933 raster: native categorical class labels.
    p=tmp_path/'ESA_WorldCover_10m_2021_v200_test_Map.tif'
    arr=np.array([[10,50],[90,95]],dtype='uint8')
    with rasterio.open(p,'w',driver='GTiff',width=2,height=2,count=1,
                       dtype='uint8',crs='EPSG:6933',nodata=0,
                       transform=from_origin(0,10000,5000,5000)) as dst:
        dst.write(arr,1)
    source,aff,n=rasterise_source([{'path':str(p),'bounds':[0,0,10000,10000]}],
                                 [0,0,10000,10000],1,px_per_cell=2)
    assert n==1
    assert np.array_equal(source,arr)
    land=np.array([[1,1],[0,1]],dtype='uint8')
    bands=aggregate_categories(source,land,2)
    assert bands.shape==(25,1,1)
    assert bands[24,0,0]==0.75
    dest=tmp_path/'wc_local_0_0_1.tif'
    check=write_tile(dest,bands,0,0,1)
    assert check['numeric_qa']=='PASS'
