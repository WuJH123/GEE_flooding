"""Annual ERA5-EX 0.1-degree source → GF10 centre-of-cell proxy.

Source 0.1° precision is retained in metadata, never called a 10km
native-resolution observation. This avoids 1.4M polygon per year.
"""
from __future__ import annotations
from pathlib import Path
import os,re
import numpy as np
import pandas as pd
from pyproj import Transformer
from .core import read_json,json_write,safe_hash,file_identity,grid_indices

def _nearest(sorted_values,targets):
    a=np.asarray(sorted_values,float)
    if not np.all(np.diff(a)>0):raise ValueError('Coordinate not strictly ascending')
    ii=np.searchsorted(a,targets)
    hi=np.clip(ii,0,len(a)-1)
    lo=np.clip(ii-1,0,len(a)-1)
    return np.where(np.abs(a[lo]-targets)<=np.abs(a[hi]-targets),lo,hi)

def _coordinate_arrays(g):
    if 'longitude' in g and 'latitude' in g:
        lon=pd.to_numeric(g.longitude,errors='coerce').to_numpy(float)
        lat=pd.to_numeric(g.latitude,errors='coerce').to_numpy(float)
        if np.isfinite(lon).all() and np.isfinite(lat).all():return lon,lat
    tr=Transformer.from_crs(6933,4326,always_xy=True)
    return tr.transform((g.grid_x.to_numpy()+.5)*10000,(g.grid_y.to_numpy()+.5)*10000)

def extract(source,grid,out,var,years,allow_grid_subset=False):
    import xarray as xr
    src=Path(source)
    if not src.is_file():raise FileNotFoundError(src)
    g=grid_indices(pd.read_parquet(grid))
    if not allow_grid_subset and len(g)!=1_395_471:
        raise ValueError('Wrong full frozen GF10; use pilot flag for tests')
    lon,lat=_coordinate_arrays(g)
    if not np.isfinite(lon).all() or not np.isfinite(lat).all():raise ValueError('GF10 centre transformation failed')
    try:
        d=xr.open_dataset(src,engine='netcdf4',decode_times=True)
    except (ImportError,ValueError) as e:
        # Test-only/source-compatible fallback; 2026 ERA5EX is normally NetCDF4.
        try:d=xr.open_dataset(src,engine='scipy',decode_times=True)
        except Exception:raise e
    try:
        if var=='auto':
            candidates=[k for k,v in d.data_vars.items() if v.ndim>=3]
            if len(candidates)!=1:
                raise ValueError('Choose --variable from '+str(list(d.data_vars)))
            var=candidates[0]
        if var not in d:raise KeyError(f'Missing ERA5-EX variable {var}; available={list(d.data_vars)}')
        da=d[var]
        lat_name=next((s for s in ('latitude','lat') if s in da.dims),None)
        lon_name=next((s for s in ('longitude','lon') if s in da.dims),None)
        time_name=next((s for s in ('year','time') if s in da.dims),None)
        if not all((lat_name,lon_name,time_name)) or da.ndim!=3:
            raise ValueError('Expected 3D source year/time × latitude × longitude')
        lons=d[lon_name].values.astype(float)
        lats=d[lat_name].values.astype(float)
        # Source users reported 0..359.9; use actual source coordinate instead of guessing.
        sample_lon=(lon%360) if lons.min()>=0 and lons.max()>180 else lon
        if lons[0]>lons[-1]:
            flip_lon=True;lons=lons[::-1]
        else:flip_lon=False
        if lats[0]>lats[-1]:
            flip_lat=True;lats=lats[::-1]
        else:flip_lat=False
        jj=_nearest(lons,sample_lon)
        # Treat longitude as periodic near the 0°/360° seam, otherwise
        # a 359.99° GF10 centre might be assigned to 359.9° instead of 0°.
        dist_current=np.abs(lons[jj]-sample_lon)
        dist_first=np.abs(((sample_lon-lons[0]+180)%360)-180)
        jj=np.where(dist_first<dist_current,0,jj)
        dist_current=np.abs(((sample_lon-lons[jj]+180)%360)-180)
        dist_last=np.abs(((sample_lon-lons[-1]+180)%360)-180)
        jj=np.where(dist_last<dist_current,len(lons)-1,jj)
        ii=_nearest(lats,lat)
        # Variables are annual climate indicators. Full-year values for 2024
        # cannot be used as 2024 early-event forecasting features.
        vals=d[time_name].values
        years_source=pd.DatetimeIndex(vals).year if np.issubdtype(vals.dtype,np.datetime64) else np.asarray(vals,dtype=int)
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        tag={'source':file_identity(src),'variable':var,'years':list(years),'grid':str(Path(grid).resolve()),'method':'nearest_source_0.1degree_centre'}
        job=safe_hash(tag)
        manifest=out/'job.json'
        if manifest.exists():
            if read_json(manifest).get('job_id')!=job:raise ValueError('Annual output version belongs to different input')
        else:json_write(manifest,{'job_id':job,**tag})
        completed=[]
        for year in years:
            if year not in years_source:raise ValueError(f'Year not in source: {year}')
            dst=out/f'year_{int(year)}.parquet'
            if dst.exists():completed.append(int(year));continue
            idx=int(np.where(years_source==year)[0][0])
            layer=da.isel({time_name:idx}).transpose(lat_name,lon_name).values
            if flip_lat:layer=layer[::-1,:]
            if flip_lon:layer=layer[:,::-1]
            result=layer[ii,jj]
            outdf=pd.DataFrame({'grid_id':g.grid_id.to_numpy(),
                                'source_year':int(year),
                                var:np.asarray(result,dtype=np.float32)})
            temp=dst.with_suffix('.writing')
            outdf.to_parquet(temp,index=False,compression='zstd')
            os.replace(temp,dst)
            completed.append(int(year))
        qa={'status':'YEARLY_0P1DEG_PROXY_NOT_GF10_NATIVE',
            'years':completed,'source_name':src.name,'variable':var,
            'source_unit':str(da.attrs.get('units','UNVERIFIED')),
            'source_crs':'EPSG:4326','resampling':'nearest_0.1degree_cell_center',
            'source_epoch':'annual_complete_year','publication_ready':False}
        json_write(out/'run_qc.json',qa)
        return qa
    finally:d.close()
