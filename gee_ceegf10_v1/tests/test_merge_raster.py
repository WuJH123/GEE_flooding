import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import Affine
import pytest
from ceegee.merge import _read_band_values


def fixture_raster():
    arr=np.array([[[1.,2.],[3.,4.]],[[5.,6.],[7.,8.]]],dtype='float32')
    mem=MemoryFile()
    with mem.open(driver='GTiff',height=2,width=2,count=2,dtype='float32',
                  crs='EPSG:6933',transform=Affine(10000,0,0,0,-10000,10000),nodata=-9999) as ds:
        ds.write(arr)
        ds.set_band_description(1,'a');ds.set_band_description(2,'b')
    return mem


def test_frozen_gf10_center_lookup_and_no_overlap():
    mem=fixture_raster()
    result={'a':np.full(4,np.nan,dtype='float32'),
            'b':np.full(4,np.nan,dtype='float32')}
    seen=np.zeros(4,dtype='uint8')
    with mem.open() as ds:
        n=_read_band_values(ds,np.array([0,1,0,1]),np.array([0,0,-1,-1]),
                             ['a','b'],result,seen,np.arange(4))
        assert n==4
        assert result['a'].tolist()==[1.,2.,3.,4.]
        assert result['b'].tolist()==[5.,6.,7.,8.]
        with pytest.raises(ValueError,match='overlap'):
            _read_band_values(ds,np.array([0,1,0,1]),np.array([0,0,-1,-1]),
                             ['a','b'],result,seen,np.arange(4))
    mem.close()


def test_bad_grid_origin_is_rejected():
    m=MemoryFile()
    with m.open(driver='GTiff',height=1,width=1,count=2,dtype='float32',
                crs='EPSG:6933',transform=Affine(10000,0,100,0,-10000,10000)) as ds:
        ds.write(np.ones((2,1,1),dtype='float32'))
    with m.open() as ds, pytest.raises(ValueError,match='origin'):
        _read_band_values(ds,np.array([0]),np.array([0]),['a','b'],
                         {'a':np.empty(1),'b':np.empty(1)},np.zeros(1,dtype='uint8'),np.arange(1))
    m.close()
