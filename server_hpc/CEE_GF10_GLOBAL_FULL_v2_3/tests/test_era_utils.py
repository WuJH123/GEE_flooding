import numpy as np
from ceeall.era import _nearest

def test_nearest_ascending_descending():
    source=np.array([1.,2.,3.])
    assert _nearest(source,np.array([1.2,2.6,3.3])).tolist()==[0,2,2]
    assert _nearest(source[::-1],np.array([1.2,2.6,3.3])).tolist()==[2,0,0]
