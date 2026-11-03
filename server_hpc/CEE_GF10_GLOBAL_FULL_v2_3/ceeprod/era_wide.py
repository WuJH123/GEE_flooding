"""Annual ERA5-EX: all available native indices to GF10 by source-cell centre.

Outputs YEAR-WIDE partitioned parquet (34 cols) not 34*76 overlapping
Parquet products. This is a 0.1 degree source proxy, never 10km native data.
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import os
import numpy as np
import pandas as pd
from .shared import prepare_directory,write_json,read_json,file_identity
from ceeall.era import _nearest,_grid_lonlat


def _catalogue(directory):
    import xarray as xr
    paths=sorted(Path(directory).rglob('*.nc'))
    if not paths:raise FileNotFoundError('No original ERA5-EX .nc staged under '+str(directory))
    result={};years=[]
    for src in paths:
        with xr.open_dataset(src,engine='netcdf4',decode_cf=True) as ds:
            y=next((k for k in ('year','time') if k in ds.coords),None)
            lat=next((k for k in ('latitude','lat') if k in ds.coords),None)
            lon=next((k for k in ('longitude','lon') if k in ds.coords),None)
            if not y or not lat or not lon:raise ValueError('Missing native ERA5EX coordinates '+str(src))
            names=[name for name,da in ds.data_vars.items() if set(da.dims)=={y,lat,lon}]
            if len(names)!=1:raise ValueError('Expected exactly one 3-D index per NetCDF: '+str(src))
            arr=ds[y].values
            yr=pd.DatetimeIndex(arr).year.to_numpy() if np.issubdtype(np.asarray(arr).dtype,np.datetime64) else np.asarray(arr).astype(int)
            if len(np.unique(yr))!=len(yr):raise ValueError('Duplicate time coordinate '+str(src))
            name=names[0].lower()
            if name in result:raise ValueError('Duplicate annual climate index '+name)
            unit=str(ds[names[0]].attrs.get('units','UNVERIFIED_SOURCE_UNIT'))
            result[name]={'source':str(src),'file_identity':file_identity(src),'variable':names[0],
                  'years':yr.tolist(),'coordinates':[y,lat,lon],'unit':unit}
            years.append(set(map(int,yr)))
    common=sorted(set.intersection(*years))
    if not common:raise ValueError('No years common across all ERA5EX indices')
    return result,common


def _one(task):
    import xarray as xr
    gridfile,varspec,year,out,job_id=task
    out=Path(out);dst=out/f'year_{year}.parquet';qc=out/f'year_{year}.qc.json'
    if dst.exists() and qc.exists():
        meta=read_json(qc)
        if meta.get('job_id')!=job_id or meta.get('status')!='OK':raise ValueError('Annual QC fingerprint mismatch: '+str(dst))
        import pyarrow.parquet as pq
        if pq.ParquetFile(dst).metadata.num_rows!=meta.get('n_grid'):
            raise ValueError('Existing ERA5EX yearly Parquet row mismatch')
        return {'status':'REUSED','year':year,'n_grid':meta['n_grid']}
    if dst.exists() or qc.exists():raise FileExistsError('Unpaired annual source products: '+str(dst))
    grid=pd.read_parquet(gridfile,columns=['grid_id','grid_x','grid_y'])
    lon,lat=_grid_lonlat(grid)
    frame=pd.DataFrame({'grid_id':grid.grid_id.to_numpy(),'source_year':np.full(len(grid),year,dtype='int16')})
    if not np.isfinite(lon).all() or not np.isfinite(lat).all():raise ValueError('GF10 center geocoding invalid')
    for name,meta in varspec.items():
        with xr.open_dataset(meta['source'],engine='netcdf4',decode_cf=True) as ds:
            var=ds[meta['variable']]
            yy,ll,oo=meta['coordinates']
            yr=meta['years'];index=yr.index(int(year))
            source_lon=np.asarray(ds[oo].values,float)
            source_lat=np.asarray(ds[ll].values,float)
            if not (source_lon.ndim==source_lat.ndim==1):raise ValueError('ERA source coords must 1D')
            if abs(np.mean(np.diff(source_lon)))>.2 or abs(np.mean(np.diff(source_lat)))>.2:
                raise ValueError('ERA5-EX invalid global coordinate spacing')
            lon0=lon%360 if source_lon.max()>180 else lon
            # Source longitude may be descending; nearest wrap at dateline.
            if source_lon[0]>source_lon[-1]:
                source_lon=source_lon[::-1];flipx=True
            else:flipx=False
            if source_lat[0]>source_lat[-1]:
                source_lat=source_lat[::-1];flipy=True
            else:flipy=False
            jj=_nearest(source_lon,lon0)
            if source_lon.max()>180:
                diff_first=np.abs((lon0-source_lon[0]+180)%360-180)
                diff_last=np.abs((lon0-source_lon[-1]+180)%360-180)
                current=np.abs((lon0-source_lon[jj]+180)%360-180)
                jj=np.where(diff_first<current,0,jj)
                jj=np.where(diff_last<np.abs((lon0-source_lon[jj]+180)%360-180),len(source_lon)-1,jj)
            ii=_nearest(source_lat,lat)
            array=var.isel({yy:index}).transpose(ll,oo).values
            if flipx:array=array[:,::-1]
            if flipy:array=array[::-1,:]
            values=np.asarray(array[ii,jj],dtype='float32')
            fill=var.attrs.get('_FillValue')
            if fill is not None:values=np.where(values==fill,np.nan,values)
            if np.isinf(values).any():raise ValueError('Infinite climate values '+name)
            frame['era5ex_'+name]=values
    if frame.grid_id.duplicated().any() or len(frame)!=1_395_471:
        raise ValueError('Annual 34-column table lost global GF10 identities')
    dest=dst.with_suffix('.writing.parquet');frame.to_parquet(dest,index=False,compression='zstd');os.replace(dest,dst)
    write_json(qc,{'status':'OK','job_id':job_id,'n_grid':len(frame),'n_climate_variables':len(varspec),
      'source_year':year,'method':'native_ERA5EX_0p1deg_nearest_source_cell','known_time_leakage_if_event_year_as_predictor':True,
      'publication_ready_without_temporal_design':False})
    return {'status':'WROTE','year':year,'n_grid':len(frame)}


def run(root,workers=2):
    root=Path(root)
    catalog,years=_catalogue(root/'data/staged/cee_all')
    # Contract is 34 fields. Stop rather than silently shipping 12/34 fields.
    if len(catalog)!=34:raise ValueError(f'ERA5-EX source catalogue found {len(catalog)} native indices, expected 34; inspect archive and metadata')
    if not 1<=workers<=4:raise ValueError('Limit per-year independent NetCDF workers to 1..4 for 128GB RAM')
    output,job_id=prepare_directory(root/'data/derived/cee_all_global_v2/era5ex_annual_wide',
       {'frozen_grid':file_identity(root/'gf10_global_nonantarctic_land.parquet'),
        'variables':catalog,'algorithm':'native 0.1degree nearest source v2'})
    write_json(output/'source_catalogue.json',catalog)
    tasks=[(str(root/'gf10_global_nonantarctic_land.parquet'),catalog,int(y),str(output),job_id) for y in years]
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_one,t) for t in tasks]
        for i,f in enumerate(as_completed(futures),1):
            z=f.result();results.append(z)
            print(f'[era5ex annual] {i}/{len(years)} years, latest={z["year"]}',flush=True)
    if len(results)!=len(years):raise ValueError('Yearly output incomplete')
    qc={'status':'ALL_SOURCE_YEARS_ERA5EX_0P1DEG_PROXY','n_years':len(years),'years':years,
      'n_variables':len(catalog),'n_grid_per_year':1_395_471,
      'storage':'per_year_wide_34_float_columns','publication_ready_for_causal_event_day':False}
    write_json(output/'run_qc.json',qc)
    return qc
