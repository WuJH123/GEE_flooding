import numpy as np
import pytest
from ceeall.morphology import _moments

def test_mean_std_and_full_mask():
    a=np.array([[0.,1.,2.],[3.,4.,5.],[6.,7.,8.]])
    o=_moments(a,window=3)
    assert o['mean'][1,1]==pytest.approx(4)
    assert o['std'][1,1]==pytest.approx(np.std(a))
    assert o['valid_fraction'][1,1]==pytest.approx(1.0)
    assert o['valid_fraction'][0,0]==pytest.approx(4/9)

def test_mask_excludes_nodata_and_valid_zero():
    a=np.array([[0.,1.,np.nan],[5.,9.,7.]])
    o=_moments(a,window=1)
    assert o['mean'][0,0]==pytest.approx(0)
    assert np.isnan(o['mean'][0,2])
    m=np.array([[False,True,True],[True,True,True]])
    q=_moments(a,window=1,mask=m)
    assert np.isnan(q['mean'][0,0])
    assert q['valid_fraction'][0,0]==0

def test_bad_windows_and_shapes():
    with pytest.raises(ValueError):_moments(np.ones((2,2)),window=2)
    with pytest.raises(ValueError):_moments(np.ones(3),window=3)
    with pytest.raises(ValueError):_moments(np.ones((2,2)),mask=np.ones(3))
