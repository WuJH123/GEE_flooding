import ast
from pathlib import Path
import numpy as np,rasterio,pytest
from rasterio.transform import Affine
from ceeprodgee.qc import check_raster
from ceeprodgee.contract import WC_BANDS

def test_offline_ee_graph_declares_final_imerg_and_mm_conversion():
 src=(Path(__file__).parents[1]/'ceeprodgee'/'ee_model.py').read_text()
 assert "'status','permanent'" in src
 assert "multiply(0.5)" in src
 assert "group.count().eq(6)" in src
 assert "date.advance(-14,'day')" in src
 assert "date.advance(-1,'day')" in src
 assert "'total_precipitation_sum'" in src
 ast.parse(src)

def test_registered_manifest_can_authenticate_unlabeled_raster(tmp_path):
 n=5; x0=1097;y0=367
 a=np.zeros((25,n,n),dtype='float32')
 a[0]=1;a[11]=1;a[12]=1;a[23]=1;a[24]=1
 p=tmp_path/'a.tif'
 with rasterio.open(p,'w',driver='GTiff',width=n,height=n,count=25,dtype='float32',crs='EPSG:6933',
  transform=Affine(10000,0,x0*10000,0,-10000,(y0+n)*10000),nodata=-9999) as ds:
  ds.write(a)
 with pytest.raises(ValueError,match='Missing band'):check_raster(p,'worldcover',x0,y0,n)
 assert check_raster(p,'worldcover',x0,y0,n,expected_manifest=WC_BANDS)['numeric_qa']=='PASS'
