"""Built-form window moments; SciPy is optional at import time but required for production.

Previous package imported scipy.ndimage at module-import time, crashing pytest
collection when the server environment did not install scipy. v1.1 imports
lazily inside the computation and preflight installs & checks SciPy first.
"""
from __future__ import annotations
import numpy as np

def _moments(array, window=3, mask=None):
    """Return window mean, std, and valid fraction without mixing nodata into zero.

    Edge handling: constant zero padded numerator AND denominator, excluding
    missing/off-grid pixels. Mask: True = valid. 2D fixed-scale raster only.
    """
    from scipy.ndimage import uniform_filter
    values=np.asarray(array,dtype=float)
    if values.ndim!=2:raise ValueError('2D raster expected')
    if not isinstance(window,int) or window<1 or window%2!=1:raise ValueError('Odd positive window required')
    valid=np.isfinite(values)
    if mask is not None:
        m=np.asarray(mask,dtype=bool)
        if m.shape!=values.shape:raise ValueError('Mask shape mismatch')
        valid &= m
    a=np.where(valid,values,0.)
    w=window*window
    n=uniform_filter(valid.astype(float),window,mode='constant',cval=0)*w
    sm=uniform_filter(a,window,mode='constant',cval=0)*w
    sq=uniform_filter(a*a,window,mode='constant',cval=0)*w
    mean=np.divide(sm,n,out=np.full(values.shape,np.nan),where=n>0)
    second=np.divide(sq,n,out=np.full(values.shape,np.nan),where=n>0)
    std=np.sqrt(np.maximum(second-mean**2,0))
    return {'mean':mean,'std':std,'valid_fraction':n/w}

def neighborhood_values(values,window=3,mask=None):
    return _moments(values,window=window,mask=mask)
