import numpy as np
import pytest
from ceeprodgee.worldcover_local import aggregate_categories
from ceeprodgee.worldcover_derived import derive,COMPOSITES


def test_one_pass_10m_categorical_bands_and_real_land():
    src=np.array([[10,50,80,80],[10,50,95,0],[90,95,50,80],[30,40,50,0]],dtype='uint8')
    land=np.array([[1,1,0,0],[1,1,1,0],[1,1,1,0],[1,1,1,0]],dtype='uint8')
    z=aggregate_categories(src,land,px_per_cell=2)
    assert z.shape==(25,2,2)
    assert z[0,0,0]==.5
    assert z[4,0,0]==.5
    assert z[24,0,1]==.25
    assert z[21,0,1]==1.0 # land only class 95
    assert np.allclose(z[:11].sum(axis=0),z[11])
    where=z[24]>0
    assert np.allclose(np.nan_to_num(z[12:23]).sum(axis=0)[where],z[23][where])

def test_worldcover_derived_no_overly_broad_green_and_no_zeros_for_missing():
    import pandas as pd
    data={f'wc_{k}_fraction_{suffix}':[.1,np.nan] for k in (10,20,30,40,50,60,70,80,90,95,100) for suffix in ('land','fullcell')}
    out=derive(pd.DataFrame(data))
    assert out.wc_green_noncrop_fraction_land.iloc[0]==pytest.approx(.5)
    assert out.wc_wetland_fraction_land.iloc[0]==pytest.approx(.2)
    assert np.isnan(out.wc_green_noncrop_fraction_land.iloc[1])
