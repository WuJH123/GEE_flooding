"""ERA5-EX annual source-cell sampling; does not create 10km-native observations."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .common import verify_frozen_grid, fidentity,atomic_parquet,atomic_json,ensure_job

def _nearest(v,t):
    """Nearest index in strict ascending/descending 1-D source coordinate."""
    v=np.asarray(v,dtype='float64');t=np.asarray(t,dtype='float64')
    if len(v)<2:raise ValueError('Coordinate requires >1 elements')
    if v[0]>v[-1]:return len(v)-1-_nearest(v[::-1],t)
    idx=np.searchsorted(v,t);right=np.clip(idx,0,len(v)-1);left=np.clip(idx-1,0,len(v)-1)
    return np.where(np.abs(v[left]-t)<=np.abs(v[right]-t),left,right)

def _grid_lonlat(g):
    from pyproj import Transformer
    tr=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True)
    lon,lat=tr.transform((g.grid_x.to_numpy()+0.5)*10000,
                         (g.grid_y.to_numpy()+0.5)*10000)
    if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
        raise ValueError('Some GF10 centres could not transform to lon/lat')
    return lon,lat

def run(root,years=(2021,2022,2023),files=None,max_vars=None,strict_grid=True,
        max_rows=None):
    import xarray as xr
    import pandas as pd
    root=Path(root)
    grid,_=verify_frozen_grid(root/'gf10_global_nonantarctic_land.parquet',strict_grid)
    if max_rows is not None:grid=grid.head(max_rows).copy()
    lon,lat=_grid_lonlat(grid)
    folder=root/'data/staged/cee_all'
    paths=sorted(folder.rglob('*_1950_2025.nc')) if files is None else [Path(p) for p in files]
    if not paths:raise FileNotFoundError('ERA5EX netcdf not extracted. Run stage era5ex first')
    if max_vars:paths=paths[:max_vars]
    result=[]
    for path in paths:
        with xr.open_dataset(path,engine='netcdf4',mask_and_scale=True) as ds:
            ncvars=list(ds.data_vars)
            y_dim=next((k for k in ('year','time') if k in ds.coords),None)
            lat_dim=next((k for k in ('latitude','lat') if k in ds.coords),None)
            lon_dim=next((k for k in ('longitude','lon') if k in ds.coords),None)
            if not all((y_dim,lat_dim,lon_dim)):
                raise ValueError('Unrecognized ERA5EX dimensions '+str(tuple(ds.dims)))
            ycoord=ds[y_dim].values
            yr=pd.to_datetime(ycoord).year.to_numpy() if np.issubdtype(np.asarray(ycoord).dtype,np.datetime64) else np.asarray(ycoord).astype(int)
            unique=list(dict.fromkeys(yr))
            if len(unique)!=len(yr):raise ValueError('Duplicate ERA5EX annual time coordinate')
            dim_candidates=[k for k in ncvars if set(ds[k].dims)=={y_dim,lat_dim,lon_dim}]
            if len(dim_candidates)!=1:raise ValueError('Expected exactly one 3D source data var: '+str(dim_candidates))
            variable=dim_candidates[0]
            lon_native=np.asarray(ds[lon_dim].values,dtype=float)
            lat_native=np.asarray(ds[lat_dim].values,dtype=float)
            if lon_native.ndim!=1 or lat_native.ndim!=1:
                raise ValueError('Source coordinates must be regular 1D')
            if len(lon_native)<100 or len(lat_native)<100:raise ValueError('Not global 0.1-degree netCDF')
            if abs(np.diff(lon_native).mean())>.111 or abs(np.diff(lat_native).mean())>.111:
                raise ValueError('Source resolution is not approximately 0.1 degree')
            lon_v=(lon+360)%360 if np.nanmin(lon_native)>=0 else lon
            li=_nearest(lon_native,lon_v);yi=_nearest(lat_native,lat)
            # longitude cyclic seam (0 .. 359.9); 359.96 is nearer 0 than 359.9.
            if np.nanmin(lon_native)>=0 and np.nanmax(lon_native)>359:
                dist=np.abs(lon_native[li]-lon_v)
                other=np.abs((lon_v-lon_native[0]+180)%360-180)
                li=np.where(other<dist,0,li)
            for year in years:
                idx=np.where(yr==year)[0]
                if len(idx)!=1:
                    raise ValueError(f'Requested ERA5EX year {year} not in {path.name}')
                # A 5,000-grid pilot must NEVER occupy the full-global folder.
                # Previously the subsequent full run encountered a job fingerprint
                # conflict and users could mistake partial yearly files for global.
                kind='era5ex_pilot' if max_rows is not None else 'era5ex'
                out=root/'data/derived/cee_all_v11'/kind/path.stem
                job=ensure_job(out,{'source':fidentity(path),'grid':fidentity(root/'gf10_global_nonantarctic_land.parquet'),
                                   'method':'native_0p1_nearest_source_cell_v11','max_rows':max_rows})
                dst=out/f'year_{year}.parquet'
                if dst.exists():
                    import pyarrow.parquet as pq
                    if pq.ParquetFile(dst).metadata.num_rows!=len(grid):raise ValueError('Existing ERA5EX year has unexpected row count')
                    result.append({'source':path.name,'year':year,'status':'REUSED'});continue
                a=np.asarray(ds[variable].isel({y_dim:int(idx[0])}).transpose(lat_dim,lon_dim).values,dtype=float)
                if a.shape!=(len(lat_native),len(lon_native)):raise ValueError('ERA5EX shape mismatch')
                v=a[yi,li];v[~np.isfinite(v)]=np.nan
                col=f'era5ex_{variable}_{year}'
                df=pd.DataFrame({'grid_id':grid.grid_id.to_numpy(),'year':int(year),col:v})
                atomic_parquet(df,dst)
                atomic_json(out/f'year_{year}_qc.json',{'job_id':job,'status':'ANNUAL_COMPLETE_NATIVE_0P1_NEAREST',
                    'variable':variable,'source_units':ds[variable].attrs.get('units','NOT_DECLARED'),
                    'source_calendar_year':int(year),'rows':len(df),'valid_rows':int(np.isfinite(v).sum()),
                    'not_true_10km_resolution':True,'not_land_centroid':True,'publication_ready':False})
                result.append({'source':path.name,'year':int(year),'status':'WROTE','valid':int(np.isfinite(v).sum())})
    atomic_json(root/'reports/cee_era5ex_v11.json',{'status':'PRODUCED_ANNUAL_SOURCE_GRID_PROXY_NEEDS_QA','results':result})
    return {'products':len(result),'written':sum(r['status']=='WROTE' for r in result)}
