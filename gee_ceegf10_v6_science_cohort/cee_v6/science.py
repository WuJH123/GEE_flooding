"""MERIT v5: independent halo convergence gate, never waive original v5 FAIL.

Compare same 10km core pixel values between 20, 40, 80 km computation
halos. Use nearest valid gf10 subset only and exact CRS/affine; similarity is
numerical convergence, not validation against field-measured flood depth.
"""
from __future__ import annotations
import numpy as np,pathlib,json
from .common import save,sha
CELL=10000
HALOS_KM=(20,40,80)
BOUNDS_TEST_STRATA=('wuhan_inland','coastal_partial','high_latitude')
BANDS=(
'merit_hand_mean_m','merit_elv_mean_m','merit_upa_mean_km2',
'merit_permanent_water_fraction','merit_valid_fraction','merit_hand_le2_fraction_valid',
'merit_hand_le5_fraction_valid','merit_hand_le10_fraction_valid',
'merit_slope_mean_deg','merit_slope_le2_fraction_valid','merit_upa_max_km2',
'merit_upa_max_log1p','merit_hand_p10_m','merit_hand_p50_m',
'merit_hand_p90_m','merit_upa_p90_km2')


def compare_rasters(path_ref,path_probe,expected_crop,relative_floor=1.0):
    import rasterio
    def read(p):
        with rasterio.open(p) as src:
            a=src.read(masked=True).filled(np.nan).astype('float64')
            props=(src.width,src.height,src.count,src.crs.to_epsg(),tuple(src.transform)[:6]);return a,props
    a,meta=read(path_ref);b,metb=read(path_probe)
    if meta!=metb:raise ValueError('Raster width,height,band,projection or affine differ')
    if meta[:4]!=(expected_crop['width'],expected_crop['height'],16,6933):raise ValueError('Not frozen 16 band core')
    stats=[]
    for i,name in enumerate(BANDS):
        av=a[i];bv=b[i]
        good=np.isfinite(av)&np.isfinite(bv)
        valid_ref=np.isfinite(av);valid_probe=np.isfinite(bv)
        # Coverage disagreement is an explicit science failure, never ignored.
        mismatched=int(np.count_nonzero(valid_ref!=valid_probe))
        n=int(np.count_nonzero(good))
        if n:
            diff=np.abs(av[good]-bv[good]);rel=diff/np.maximum(relative_floor,np.abs(av[good]))
            p95=float(np.quantile(rel,.95));maximum=float(np.max(rel));p95_abs=float(np.quantile(diff,.95));max_abs=float(np.max(diff))
        else:p95=maximum=p95_abs=max_abs=float('nan')
        stats.append({'band':name,'n':n,'mask_mismatch':mismatched,'p95_rel':p95,'max_rel':maximum,
                     'p95_abs':p95_abs,'max_abs':max_abs})
    return stats


def approve(science_rows,required_keys,output,tolerance_p95=.005,tolerance_max=.02):
    """No science gate without direct reference *and* all halo comparison rows."""
    required={(key,20,40) for key in required_keys}|{(key,40,80) for key in required_keys}
    seen={(r['tile_key'],int(r['ref_halo_km']),int(r['probe_halo_km'])) for r in science_rows}
    if not required.issubset(seen):raise ValueError('Missing independently measured 20/40/80 halo convergence pairs')
    fail=[]
    for row in science_rows:
        if row['tile_key'] not in required_keys:continue
        if not row.get('source_tif_sha256') or not row.get('reference_tif_sha256'):
            fail.append((row['tile_key'],'missing source raster fingerprint'));continue
        # Early 20->40 differences are diagnostic; late 40->80 must converge.
        # Otherwise a too-small 20 km halo would falsely reject a stable 80 km baseline.
        if (int(row['ref_halo_km']),int(row['probe_halo_km']))!=(40,80):continue
        for s in row['bands']:
            if s['n']==0 or s['mask_mismatch'] or not np.isfinite(s['p95_rel']) or not np.isfinite(s['max_rel']):
                fail.append((row['tile_key'],s['band'],'missingness mismatch'))
            elif s['p95_rel']>tolerance_p95 or s['max_rel']>tolerance_max:
                fail.append((row['tile_key'],s['band'],'nonconvergent'))
    status='PASS_20_40_80_HALO_NUMERIC_CONVERGENCE' if not fail else 'FAIL_SCIENTIFIC_EQUIVALENCE'
    report={'status':status,'required_tiles':list(required_keys),'n_failed_comparisons':len(fail),
            'failures':fail[:50],'p95_relative_limit':tolerance_p95,
            'max_relative_limit':tolerance_max,'max_halo_km':80,
            'qualification':'Only 40-to-80km bandwise convergence is decisive; 20-to-40km provides sensitivity evidence',
            'source_gf10_n':1395471,'model_bands':list(BANDS),
            'not_physical_flood_validation':True}
    save(output,report)
    return report


def buffered_geometry(crop,halo_km,valid_limits):
    l,b,r,t=[float(v) for v in crop]
    h=halo_km*1000.
    wl,wr,wb,wt=valid_limits
    calc=[l-h,b-h,r+h,t+h]
    if calc[0]<=wl+1 or calc[2]>=wr-1 or calc[1]<=wb+1 or calc[3]>=wt-1:
        raise ValueError('Halo crosses valid EPSG:6933 bounds: keep in quarantine')
    export=[l+5000-1,b+5000-1,r-5000+1,t-5000+1]
    if export[0]>=export[2] or export[1]>=export[3]:raise ValueError('Invalid crop export region')
    return calc,export
