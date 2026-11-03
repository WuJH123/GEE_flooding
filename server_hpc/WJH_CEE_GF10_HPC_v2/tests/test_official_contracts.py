"""Source contracts and native class semantics (synthetic fixtures)."""
import json
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from gf10hpc.verify import verify_source
from gf10hpc.sources import stage_one
from zipfile import ZipFile


def mk(path,crs='ESRI:54009',resolution=1000,value=100000,dtype='uint32'):
    with rasterio.open(path,'w',driver='GTiff',width=12,height=12,count=1,
                       dtype=dtype,nodata=65535 if dtype=='uint16' else None,
                       crs=crs,transform=from_origin(0,12000,resolution,resolution)) as ds:
        ds.write(np.full((12,12),value,dtype=dtype),1)


def test_jrc_native_1km_mollweide_and_area_units(tmp_path):
    r=tmp_path/'test.tif';mk(r)
    qc=verify_source(r,'ghsl_built_2020',tmp_path/'out.json')
    assert qc['status']=='METADATA_CONTRACT_PASS_BUT_UNITS_EXTERNAL_QA_REQUIRED'
    assert qc['sample']['max']==100000
    with pytest.raises(FileExistsError):verify_source(r,'ghsl_built_2000',tmp_path/'out.json')


def test_reject_geographic_ghsl_totals_and_excess_area(tmp_path):
    r=tmp_path/'wrong.tif';mk(r,crs='EPSG:4326')
    with pytest.raises(ValueError,match='1000m World Mollweide'):
        verify_source(r,'ghsl_built_2020',tmp_path/'q.json')
    r2=tmp_path/'huge.tif';mk(r2,value=1000005*2)
    with pytest.raises(ValueError,match='>1,000,000'):
        verify_source(r2,'ghsl_built_2020',tmp_path/'q2.json')


def test_smod_code_30_valid_and_unknown_rejected(tmp_path):
    r=tmp_path/'smod.tif';mk(r,value=30,dtype='int16')
    q=verify_source(r,'ghsl_smod_2020',tmp_path/'x.json')
    assert q['sample']['unique']==[30]
    r2=tmp_path/'smod_bad.tif';mk(r2,value=31,dtype='int16')
    with pytest.raises(ValueError,match='Unrecognized'):
        verify_source(r2,'ghsl_smod_2020',tmp_path/'y.json')


def test_staged_zip_original_year_rejected(tmp_path):
    raw=tmp_path/'ghsl.tif';mk(raw)
    z=tmp_path/'GHS_BUILT_S_E2000_GLOBE_R2023A_54009_1000_V1_0.zip'
    with ZipFile(z,'w') as zz:zz.write(raw,arcname='GHS_BUILT_S_E2000_GLOBE_R2023A_54009_1000_V1_0.tif')
    dest=tmp_path/'staged.tif'
    stage_one(z,'*.tif',dest)
    with pytest.raises(ValueError,match='source year'):
        verify_source(dest,'ghsl_built_2020',tmp_path/'q.json')
    assert verify_source(dest,'ghsl_built_2000',tmp_path/'ok.json')['status']=='METADATA_CONTRACT_PASS'
