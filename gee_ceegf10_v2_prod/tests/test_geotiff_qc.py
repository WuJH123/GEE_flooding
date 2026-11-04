import numpy as np, rasterio, pytest
from rasterio.transform import Affine
from ceeprodgee.qc import check_raster
from ceeprodgee.contract import WC_BANDS,MERIT_BANDS

def _write(path,values,names,x0=1097,y0=367):
 n=values.shape[-1]
 with rasterio.open(path,'w',driver='GTiff',width=n,height=n,count=values.shape[0],dtype='float32',
                    transform=Affine(10000,0,x0*10000,0,-10000,(y0+n)*10000),crs='EPSG:6933',nodata=-9999) as dst:
  for i,nm in enumerate(names):
   dst.write(values[i].astype('float32'),i+1);dst.set_band_description(i+1,nm)

def test_worldcover_all_classes_conservation(tmp_path):
 a=np.zeros((25,5,5),dtype='float32')
 a[0]=0.4;a[7]=0.6;a[11]=1
 a[12]=0.65;a[19]=0.35;a[23]=1;a[24]=0.4
 path=tmp_path/'test.tif';_write(path,a,WC_BANDS)
 assert check_raster(path,'worldcover',1097,367,5)['numeric_qa']=='PASS'
 a[0]=0.5;_write(path,a,WC_BANDS)
 with pytest.raises(ValueError,match='conserve'):check_raster(path,'worldcover',1097,367,5)

def test_merit_physical_constraints(tmp_path):
 a=np.ones((16,10,10),dtype='float32')
 a[5]=0.1;a[6]=0.3;a[7]=0.5
 a[10]=200;a[11]=np.log1p(200)
 a[12]=1;a[13]=2;a[14]=4;a[15]=20
 path=tmp_path/'merit.tif';_write(path,a,MERIT_BANDS)
 assert check_raster(path,'merit',1097,367,10)['numeric_qa']=='PASS'
 a[5]=0.4;a[6]=0.3;_write(path,a,MERIT_BANDS)
 with pytest.raises(ValueError,match='threshold'):check_raster(path,'merit',1097,367,10)

def test_reject_misaligned_or_unlabeled(tmp_path):
 a=np.zeros((25,5,5),dtype='float32')
 a[11]=1;a[0]=1;a[12]=1;a[23]=1;a[24]=1
 path=tmp_path/'w.tif';_write(path,a,WC_BANDS)
 with pytest.raises(ValueError,match='x0 mismatch'):check_raster(path,'worldcover',1102,367,5)
 with rasterio.open(path,'r+') as ds:ds.set_band_description(1,'WRONG')
 with pytest.raises(ValueError,match='Band descriptions'):check_raster(path,'worldcover',1097,367,5)
