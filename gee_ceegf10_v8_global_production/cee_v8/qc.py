"""Strict source-key conservation; missing meteorology is NOT observed zero."""
from __future__ import annotations
import pathlib
import pandas as pd
from . import core

def weather(csv,expected,reference=None):
 p=pathlib.Path(csv);a=pd.read_csv(p,dtype={'grid_id':'string','date_utc':'string'})
 if not set(core.FIELDS)<=set(a.columns):raise ValueError('Missing weather source column(s): '+str(set(core.FIELDS)-set(a)))
 if a.duplicated(['grid_id','date_utc']).any():raise ValueError('GEE duplicate grid-date rows')
 e=expected[['grid_id','date_utc']].copy();e.grid_id=e.grid_id.astype(str);e.date_utc=e.date_utc.astype(str)
 a.grid_id=a.grid_id.astype(str);a.date_utc=a.date_utc.astype(str)
 ak=set(zip(a.grid_id,a.date_utc));ek=set(zip(e.grid_id,e.date_utc))
 if ak!=ek or len(a)!=len(e):raise ValueError(f'GEE row conservation mismatch, actual={len(a)} expected={len(e)}')
 for c in core.FIELDS[2:]:a[c]=pd.to_numeric(a[c],errors='coerce')
 counts={'imerg_n_obs_day':48,'imerg_n_obs_pre7d':336,'imerg_n_obs_pre14d':672,'imerg_n_obs_pre30d':1440}
 good=pd.Series(True,index=a.index)
 for c,n in counts.items():good &= a[c].eq(n)
 rain=['imerg_day_mm','imerg_rolling3h_max_mm','imerg_pre7d_mm','imerg_pre14d_mm','imerg_pre30d_mm']
 valid=good&a[rain].notna().all(axis=1)&a[rain].ge(-0.001).all(axis=1)
 valid &=a.imerg_rolling3h_max_mm.le(a.imerg_day_mm+0.01)
 soils=['era5_soil_l1_prevday_m3m3','era5_soil_l2_prevday_m3m3']
 era=a[soils].notna().all(axis=1)&a[soils].ge(-0.001).all(axis=1)&a[soils].le(1.001).all(axis=1)
 era &=a.era5_t2m_prevday_C.between(-90,65)
 # A masked coastal ERA5 value is missingness, not a spurious zero.
 if not bool(valid.all()):raise ValueError(f'GEE missing / implausible IMERG data in {int((~valid).sum())}/{len(a)} rows')
 q={'status':'ACCEPTED_WEATHER_COMPLETE_IMERG_MASKED_ERA5_RETAINED',
 'n_grid_dates':len(a),'n_ERA5_missing_or_invalid':int((~era).sum()),
 'n_IMERG_incomplete':int((~valid).sum()),'csv_sha256':core.sha(p),
 'source_dates_not_independently_verified':True,'news_absence_is_not_flood_absence':True}
 if reference is not None:
  b=reference.copy();b.grid_id=b.grid_id.astype(str);b.date_utc=b.date_utc.astype(str)
  z=a.merge(b,on=['grid_id','date_utc'],how='inner',suffixes=('','_v7'),validate='one_to_one')
  if len(z)!=len(b):raise ValueError('Canary did not cover all source-v7 accepted records')
  compared=0;errors={}
  for c in core.FIELDS[2:]:
   new=pd.to_numeric(z[c],errors='coerce');old=pd.to_numeric(z[c+'_v7'],errors='coerce')
   if not new.isna().equals(old.isna()):raise ValueError('V8 macro vs V7 mask mismatch in '+c)
   ok=new.notna()
   if ok.any():
    delta=(new[ok]-old[ok]).abs();tol=0.0001+old[ok].abs()*0.005
    if bool((delta>tol).any()):raise ValueError('V8 macro vs V7 numerical mismatch in '+c+' max='+str(delta.max()))
    errors[c]=float(delta.max());compared+=int(ok.sum())
  q['macro_canary_v7_numeric']='PASS';q['source_reference_max_absolute_differences']=errors;q['n_numeric_pairs']=compared
 return q

def merit(path,row):
 import rasterio
 import numpy as np
 p=pathlib.Path(path);x=int(row.crop_x0);y=int(row.crop_y0);w=int(row.width);h=int(row.height)
 with rasterio.open(p) as s:
  if s.crs is None or s.crs.to_epsg()!=6933:raise ValueError('Wrong MERIT CRS')
  if (s.width,s.height,s.count)!=(w,h,16):raise ValueError(f'Wrong MERIT rectangular crop shape {(s.width,s.height,s.count)} expected {(w,h,16)}')
  expect=(10000.,0.,x*10000.,0.,-10000.,(y+h)*10000.)
  if max(abs(float(a)-float(b)) for a,b in zip(tuple(s.transform)[:6],expect))>1e-6:raise ValueError('MERIT affine mismatch')
  a=s.read(masked=True).filled(np.nan)
 if not np.any(np.isfinite(a)):raise ValueError('MERIT positive-land tile has no valid values')
 # Reject a nominally successful export if it lacks *any* exact frozen GF10
 # land identity. Inspect the V4 crop origin and true top-down raster row.
 if 'land_ids' not in row.index or not isinstance(row['land_ids'],str):
  raise ValueError('Missing immutable per-tile GF10 land membership')
 land_ids=row['land_ids'].split(';')
 if len(land_ids)!=int(row.n_land_cells) or len(set(land_ids))!=len(land_ids):
  raise ValueError('Invalid per-tile GF10 land identity conservation')
 min_source=1.0
 for gid in land_ids:
  gx,gy=map(int,gid.split('_'))
  iy=y+h-gy-1;ix=gx-x
  if not (0<=iy<h and 0<=ix<w):raise ValueError('Frozen land ID outside MERIT raster crop: '+gid)
  if not np.isfinite(a[:,iy,ix]).any():
   raise ValueError('MERIT exported land cell has no source values: '+gid)
  if not np.isfinite(a[4,iy,ix]):
   raise ValueError('MERIT land-cell validity band absent: '+gid)
  min_source=min(min_source,float(a[4,iy,ix]))
 for i in [3,4,5,6,7,9]:
  z=a[i];b=np.isfinite(z)
  if b.any() and ((z[b]<-0.001)|(z[b]>1.001)).any():raise ValueError('Invalid ratio MERIT band '+core.BANDS[i])
 for i in [0,2,8,10,12,13,14,15]:
  z=a[i];b=np.isfinite(z)
  if b.any() and (z[b]<-0.001).any():raise ValueError('Physically negative MERIT band '+core.BANDS[i])
 return {'status':'MERIT_16_BAND_RECTANGULAR_AFFINE_QC_PASS','n_land_expected':int(row.n_land_cells),
 'n_pixels':w*h,'n_pixels_any_finite':int(np.isfinite(a).any(axis=0).sum()),
 'file_sha256':core.sha(p),'source_contract':core.BANDS,'not_flood_observation':True,
 'n_GHSHG_land_cells_verified':len(land_ids),'minimum_merit_source_valid_fraction_land':min_source}
