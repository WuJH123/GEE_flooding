"""Strict identity/unit/categorical conservation checks for downloaded GF10 GeoTIFF."""
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from .contract import WC_BANDS, MERIT_BANDS, WC_CODES

def check_raster(path,family,x0=None,y0=None,n=None,expected_manifest=None):
    import rasterio
    from rasterio.windows import Window
    expected=MERIT_BANDS if family=='merit' else WC_BANDS
    with rasterio.open(path) as r:
        if not r.crs or r.crs.to_epsg()!=6933:raise ValueError('Wrong CRS (expected EPSG6933)')
        t=r.transform
        if (abs(t.a-10000)>1e-6 or abs(t.e+10000)>1e-6 or abs(t.b)>1e-7 or abs(t.d)>1e-7):
            raise ValueError('Must be exact GF10 10km aligned raster')
        if abs(t.c/10000-round(t.c/10000))>1e-6 or abs(t.f/10000-round(t.f/10000))>1e-6:
            raise ValueError('GF10 zero origin mismatch')
        if len(expected)!=r.count:raise ValueError(f'{family} requires {len(expected)} bands, got {r.count}')
        if n is not None and (r.width!=n or r.height!=n):raise ValueError('Unexpected tile size')
        if x0 is not None and abs(t.c/10000-x0)>1e-6:raise ValueError('Tile x0 mismatch')
        if y0 is not None and abs((t.f-r.height*10000)/10000-y0)>1e-6:raise ValueError('Tile y0 mismatch')
        desc=tuple(r.descriptions)
        if any(desc) and desc!=expected:raise ValueError('Band descriptions/order changed; reject output')
        if not any(desc) and tuple(expected_manifest or ())!=expected:
            raise ValueError('Missing band descriptions and no exact registered band manifest')
        arr=r.read(masked=True)
    a=arr.filled(np.nan)
    valid=np.isfinite(a)
    if family=='merit':
        i={n:j for j,n in enumerate(expected)}
        f=[i[f'merit_hand_le{x}_fraction_valid'] for x in (2,5,10)]
        both=np.logical_and.reduce([valid[j] for j in f])
        if np.any(a[f[0]][both]>a[f[1]][both]+1e-5) or np.any(a[f[1]][both]>a[f[2]][both]+1e-5):
            raise ValueError('HAND threshold fractions not ordered')
        p=[i[f'merit_hand_p{x}_m'] for x in (10,50,90)]
        both=np.logical_and.reduce([valid[j] for j in p])
        if np.any(a[p[0]][both]>a[p[1]][both]+1e-3) or np.any(a[p[1]][both]>a[p[2]][both]+1e-3):
            raise ValueError('HAND percentiles not ordered')
        mx=i['merit_upa_max_km2']; p90=i['merit_upa_p90_km2']
        both=valid[mx]&valid[p90]
        if np.any(a[mx][both]+1e-2<a[p90][both]):raise ValueError('UPA max smaller than p90')
        log=i['merit_upa_max_log1p'];both=valid[mx]&valid[log]
        if np.any(abs(a[log][both]-np.log1p(a[mx][both]))>1e-3):raise ValueError('UPA log1p nonconservation')
        for n in ('merit_valid_fraction','merit_permanent_water_fraction',
                  'merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
                  'merit_hand_le10_fraction_valid','merit_slope_le2_fraction_valid'):
            z=a[i[n]]; good=np.isfinite(z)
            if np.any((z[good]<-1e-4)|(z[good]>1.0001)):raise ValueError('Invalid MERIT fraction: '+n)
    else:
        full=a[0:11]; full_valid=a[11]; land=a[12:23]; land_valid=a[23]; land_frac=a[24]
        if np.any(np.nanmin(a)<-1e-5) or np.any(np.nanmax(a)>1.0001):raise ValueError('Invalid WC fraction')
        good=np.all(np.isfinite(full),axis=0)&np.isfinite(full_valid)
        errfull=np.max(abs(np.sum(full[:,good],axis=0)-full_valid[good])) if np.any(good) else 0
        good=np.all(np.isfinite(land),axis=0)&np.isfinite(land_valid)
        errland=np.max(abs(np.sum(land[:,good],axis=0)-land_valid[good])) if np.any(good) else 0
        if max(errfull,errland)>0.001:raise ValueError(f'WC classes do not conserve area: {errfull},{errland}')
    return {'path':str(path),'family':family,'n_rows':int(a.shape[1]*a.shape[2]),
            'n_bands':len(expected),'fraction_valid_cells':int(np.isfinite(a[0]).sum()),
            'numeric_qa':'PASS'}
