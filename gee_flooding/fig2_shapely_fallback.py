"""Bounded, exact native pixel intersection when exactextract is unavailable.

For preverified *equal-area metre* rasters only (EPSG:6933 / ESRI:54009).
This fallback does not resample, download or alter the frozen GF10 geometry.
It is intentionally slow and limited to small grid batches; for production
prefer the tested exactextract C++ implementation.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from shapely.geometry import box, Polygon
from shapely.ops import transform as geom_transform
from pyproj import Transformer
from rasterio.windows import Window
from rasterio.transform import xy


def native_polygon(x, y, src_crs, steps=16):
    x0,y0=int(x)*10000,int(y)*10000
    corners=[(x0,y0),(x0+10000,y0),(x0+10000,y0+10000),
             (x0,y0+10000),(x0,y0)]
    edge=[]
    for a,b in zip(corners[:-1],corners[1:]):
        for i in range(steps):
            t=i/steps
            edge.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
    tr=Transformer.from_crs("EPSG:6933",src_crs,always_xy=True)
    poly=geom_transform(tr.transform,Polygon(edge))
    if poly.is_empty or not poly.is_valid or poly.area<=0:
        raise ValueError("Invalid transformed GF10 polygon")
    return poly


def read_cell(ds,poly,band,kind,classes,max_pixels=250000):
    from rasterio.windows import from_bounds
    from shapely.prepared import prep
    bounds=poly.bounds
    win=from_bounds(*bounds,transform=ds.transform)
    c0=max(0,math.floor(win.col_off))
    r0=max(0,math.floor(win.row_off))
    c1=min(ds.width,math.ceil(win.col_off+win.width))
    r1=min(ds.height,math.ceil(win.row_off+win.height))
    if c1<=c0 or r1<=r0:
        return dict(count=0.0,mean=np.nan,sum=0.0,class_share=np.nan)
    if (c1-c0)*(r1-r0)>max_pixels:
        raise ValueError("Shapely fallback exceeds bounded pixel budget; use exactextract")
    w=Window(c0,r0,c1-c0,r1-r0)
    arr=ds.read(band,window=w,masked=True)
    transform=ds.window_transform(w)
    prepared=prep(poly)
    total=0.0
    summed=0.0
    categorical=0.0
    pixel_area=abs(ds.transform.a*ds.transform.e)
    for rr in range(arr.shape[0]):
        for cc in range(arr.shape[1]):
            if np.ma.is_masked(arr[rr,cc]):continue
            value=float(arr[rr,cc])
            if not np.isfinite(value):continue
            left,top=transform @ (cc,rr)
            right,bottom=transform @ (cc+1,rr+1)
            pixel=box(min(left,right),min(top,bottom),
                      max(left,right),max(top,bottom))
            if not prepared.intersects(pixel):continue
            share=float(poly.intersection(pixel).area)/pixel_area
            if share<=0:continue
            total+=share
            summed+=value*share
            if kind=="class_fraction" and int(value) in classes:
                categorical+=share
    return dict(count=total,mean=(summed/total if total else np.nan),
                sum=summed,class_share=(categorical/total if total else np.nan))


def extract_source(ds,grid,band,kind,classes):
    # If pixel area varies by latitude, this computation is not conservation safe.
    if str(ds.crs).upper() not in {"ESRI:54009","EPSG:6933"}:
        raise ValueError("Shapely local fallback requires verified equal-area ESRI:54009 or EPSG:6933; use GEE or documented equal-area reprojection")
    if abs(ds.transform.b)>1e-12 or abs(ds.transform.d)>1e-12:
        raise ValueError("Rotated native raster not supported")
    rows=[]
    for r in grid.itertuples(index=False):
        poly=native_polygon(r.grid_x,r.grid_y,ds.crs)
        result=read_cell(ds,poly,band,kind,set(classes))
        rows.append(dict(grid_id=str(r.grid_id),**result))
    return pd.DataFrame(rows)
