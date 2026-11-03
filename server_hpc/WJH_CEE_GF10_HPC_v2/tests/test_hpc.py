import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pytest
from rasterio.transform import from_origin
import rasterio
from gf10hpc.core import grid_indices,audit_grid,tile_index
from gf10hpc.raster import _aggregate_1km,PROFILES
from gf10hpc.era import _nearest
from gf10hpc.sources import stage_one,stage_archive
from gf10hpc.gisd import _one


def test_ghsl_area_and_count_conservation():
    a=np.ones((20,20),dtype=np.float32)*1_000_000
    z,valid=_aggregate_1km(a,'pixel_m2',[],2,10)
    assert (np.asarray(z['value'])==100).all()
    assert (valid==1).all()
    p,_=_aggregate_1km(np.full((20,20),5.,dtype=np.float32),'pixel_count',[],2,10)
    assert (np.asarray(p['value'])==500).all()


def test_ghsl_categorical_not_average_codes():
    arr=np.full((20,20),21,dtype=np.float32)
    arr[0:10,0:10]=30
    z,valid=_aggregate_1km(arr,'classes',[10,11,12,13,21,22,23,30],2,10)
    assert z['30'][1,0]==0
    assert z['30'][1,1]==0
    assert z['30'][0,0]==1
    assert z['21'][0,0]==0
    assert (valid==1).all()


def test_reject_unsafe_ghsl_zip_and_repeat_staging(tmp_path):
    z=tmp_path/'test.zip'
    with ZipFile(z,'w') as f:
        f.writestr('source/one.tif',b'12345')
    dst=tmp_path/'out.tif'
    result=stage_one(z,'*.tif',dst)
    assert result['bytes']==5 and dst.read_bytes()==b'12345'
    assert stage_one(z,'*.tif',dst)['status']=='REUSED_ZIP_CRC_CHECKED'
    z2=tmp_path/'unsafe.zip'
    with ZipFile(z2,'w') as f:f.writestr('../escape.txt',b'X')
    with pytest.raises(ValueError,match='Unsafe'):
        stage_archive(z2,tmp_path/'target')


def test_era5ex_nearest_indices():
    a=np.array([-89.9,0,89.9])
    assert _nearest(a,np.array([-89.,2.,89.])).tolist()==[0,1,2]


def test_gisd_native_class_mask_before_1km_warp(tmp_path):
    arr=np.zeros((200,200),dtype=np.uint8)
    arr[:100,:]=1
    arr[100:,:100]=4
    arr[100:,100:]=8
    native=tmp_path/'GISD30_1985-2020_E0N5.tif'
    with rasterio.open(native,'w',driver='GTiff',height=200,width=200,count=1,
         crs='EPSG:4326',transform=from_origin(10,5,.0002695,.0002695),
         dtype='uint8',nodata=255,compress='deflate') as ds:ds.write(arr,1)
    result=_one(native,tmp_path/'out',gdal_threads=1)
    assert result['status']=='WROTE'
    o=tmp_path/'out'
    with rasterio.open(o/'2020'/f'gisd2020_frac_{native.stem}.tif') as ds:
        a=ds.read(1);a=a[a>=0]
        assert a.size>0 and a.min()>=0 and a.max()<=1
    with rasterio.open(o/'2000'/f'gisd2000_frac_{native.stem}.tif') as ds:
        b=ds.read(1)
    assert b.shape[0]>0


def test_grid_schema_and_hpc_tiles(tmp_path):
    pytest.importorskip('pyarrow')
    import pandas as pd
    df=pd.DataFrame({'grid_id':['-1_0','0_0','1_0'],
       'grid_x':[-1,0,1],'grid_y':[0,0,0],
       'land_area_km2':[4.,100.,.2], 'land_fraction':[.04,1,.002]})
    path=tmp_path/'grid.parquet';df.to_parquet(path,index=False)
    qc=audit_grid(path,full=False)
    assert qc['n_grid']==3
    p=tile_index(path,tmp_path/'tiles',side=16,full=False)
    assert p['n_grid']==3
    assert tile_index(path,tmp_path/'tiles',side=16,full=False)['status']=='TILES_COMPLETE'
    with pytest.raises(ValueError):tile_index(path,tmp_path/'tiles',side=32,full=False)


def test_ghsl_fast_pilot_if_arrow(tmp_path):
    pytest.importorskip('pyarrow')
    import pandas as pd
    from gf10hpc.raster import run
    # 1km equal-area SOURCE domain is Mollweide, same raw unit m²/pixel.
    path=tmp_path/'jrc_test.tif'
    with rasterio.open(path,'w',driver='GTiff',width=128,height=128,count=1,
        crs='ESRI:54009',transform=from_origin(-64000,64000,1000,1000),
        dtype='float32',nodata=-9999) as s:
        s.write(np.full((128,128),125000.,dtype=np.float32),1)
    grid=tmp_path/'grid.parquet'
    pd.DataFrame({'grid_id':['0_0','1_0'], 'grid_x':[0,1], 'grid_y':[0,0],
                  'land_area_km2':[100.,100.]}).to_parquet(grid,index=False)
    tile_index(grid,tmp_path/'tiles64',side=16,full=False)
    qa=run(tmp_path/'tiles64',[path],'ghsl_built_2020',tmp_path/'out',workers=2,
           gdal_threads=1,factor=10)
    assert qa['n_tasks']==1
    d=pd.read_parquet(next((tmp_path/'out'/'tiles').glob('*.parquet')))
    assert len(d)==2
    assert d.built_area_km2_2020.dropna().between(0,100).all()
