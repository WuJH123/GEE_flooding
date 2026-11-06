"""No completion claims without conserved keys, source hashes and seam 450 science QC."""
from __future__ import annotations
import pathlib,json
import pandas as pd
import numpy as np
from . import core,runner,qc

def weather(root,pkg,out=None,allow_partial=False):
 p=pathlib.Path(pkg);pl=p/'plans';db=core.dbopen(p/'reports'/'v8_production.sqlite')
 q=core.read_json(pl/'frozen_plan_qc.json')
 if q is None:raise ValueError('No v8 freeze')
 original=pd.read_parquet(pl/'accepted_v7_weather.parquet')
 frames=[original[core.FIELDS].copy()]
 seen=[]
 jobs=db.execute("SELECT * FROM jobs WHERE family IN ('weather','canary','canary_child') AND state='ACCEPTED'").fetchall()
 for z in jobs:
  if z['family'] in ('canary','canary_child'):continue  # canary matches already reused v7 rows
  fn=p/'downloads'/(core.RUN+'_'+z['key']+'.csv')
  if not fn.is_file() or core.sha(fn)!=z['local_sha']:raise ValueError('Accepted EE source file changed: '+str(fn))
  f=pd.read_csv(fn,dtype={'grid_id':'string','date_utc':'string'})
  if not set(core.FIELDS)<=set(f):raise ValueError('Weather source columns changed')
  frames.append(f[core.FIELDS]);seen.append(z['key'])
 res=pd.concat(frames,ignore_index=True)
 if res.duplicated(['grid_id','date_utc']).any():raise ValueError('Weather GEE output has duplicated GF10×date')
 planned=pd.read_parquet(pl/'weather_grid_days.parquet')
 keys=set(zip(res.grid_id.astype(str),res.date_utc.astype(str)))
 expected=set(zip(planned.grid_id.astype(str),planned.date_utc.astype(str)))
 legacy=set(zip(original.grid_id.astype(str),original.date_utc.astype(str)))
 if not keys<=expected|legacy:raise ValueError('Unexpected weather rows from outside v7 immutable cohort')
 missing=(expected|legacy)-keys
 if missing and not allow_partial:raise ValueError(f'Weather incomplete: missing {len(missing)} GF10×UTC proxy day rows')
 dest=pathlib.Path(out or p/'data'/'GF10_IMERG_ERA5_LAND_EVENT_EXPOSURES.parquet');dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():raise FileExistsError('Never overwrite immutable production panel')
 res.to_parquet(dest,index=False)
 report={'status':'COMPLETE_EXPOSURE_PREEXTRACTION_WITH_SOURCE_UNCERTAINTY' if not missing else 'PARTIAL_WEATHER_NOT_GLOBAL_COMPLETE',
  'rows':len(res),'expected_rows':len(expected|legacy),'missing':len(missing),'unique_GF10_days':True,
  'source_UTC_date_proxy':True,'not_confirmed_dry_controls':True,
  'independent_physical_flood_validation':False,'output_sha256':core.sha(dest),
  'v8_batch_sources':len(seen),'v7_source_rows_reused':len(original)}
 core.write_json(dest.with_suffix('.qc.json'),report)
 return report

def merit(root,pkg,out=None,allow_partial=False):
 import rasterio
 files=core.root_files(root);p=pathlib.Path(pkg)
 allgrid=core.validate_grid(files['grid'])
 old=files['v7']/'data'/'merit_v7_batch5_accepted_partial.parquet'
 if not old.is_file():raise FileNotFoundError('V7 863 accepted cells source required: '+str(old))
 frozen=core.read_json(p/'plans'/'frozen_plan_qc.json')
 if not frozen or core.sha(old)!=frozen.get('v7_accepted_merit_parquet_sha256'):
  raise ValueError('Accepted 863-cell V7 source has changed since V8 plan freezing')
 base=pd.read_parquet(old)
 if len(base)!=863 or base.grid_id.duplicated().any():raise ValueError('V7 863-cell acceptance changed')
 base=base[['grid_id']+[x for x in core.BANDS if x in base.columns]].copy()
 if not set(core.BANDS)<=set(base):raise ValueError('V7 science-accepted MERIT source missing bands')
 batches=[];db=core.dbopen(p/'reports'/'v8_production.sqlite')
 for z in db.execute("SELECT * FROM jobs WHERE family='merit' AND state='ACCEPTED'"):
  fp=p/'downloads'/(core.RUN+'_'+z['key']+'.tif')
  if core.sha(fp)!=z['local_sha']:raise ValueError('MERIT accepted source hash changed')
  row=runner.merit_row(p,z['key']); x=int(row.crop_x0);y=int(row.crop_y0);w=int(row.width);h=int(row.height)
  with rasterio.open(fp) as ds:a=ds.read(masked=True).filled(np.nan)
  records=[]
  for iy in range(h):
   for ix in range(w):
    g=f'{x+ix}_{y+h-iy-1}'
    if not np.isfinite(a[:,iy,ix]).any():continue
    records.append((g,*map(float,a[:,iy,ix])))
  batches.extend(records)
 output=pd.DataFrame(batches,columns=['grid_id']+core.BANDS)
 if output.grid_id.duplicated().any() or base.grid_id.astype(str).isin(output.grid_id).any():raise ValueError('MERIT tile overlaps old accepted cells')
 merged=pd.concat([base,output],ignore_index=True)
 ids=set(allgrid.grid_id.astype(str));got=set(merged.grid_id.astype(str))
 if not got<=ids:raise ValueError('MERIT output cells not part of frozen GF10')
 missing=ids-got
 # 14 V4 quarantine meridian blocks are never silently considered complete.
 seam_file=p/'reports'/'seam450_independent_science_ACCEPTED.parquet'
 if seam_file.exists():
  seam=pd.read_parquet(seam_file)
  if seam.grid_id.duplicated().any() or not set(core.BANDS)<=set(seam):raise ValueError('Invalid seam acceptance table')
  if set(seam.grid_id.astype(str))&got:raise ValueError('Seam cells conflict with accepted safe MERIT')
  if len(seam)!=450 or not core.read_json(seam_file.with_suffix('.qc.json'),{}).get('independent_science_pass'):
   raise ValueError('Seam recovery needs independently verified 450-cell source and QC')
  merged=pd.concat([merged,seam[['grid_id']+core.BANDS]],ignore_index=True)
  got=set(merged.grid_id.astype(str));missing=ids-got
 if missing and not allow_partial:raise ValueError(f'MERIT incomplete: {len(missing)} frozen land grid cells not accepted (includes seam quarantine if unresolved)')
 dest=pathlib.Path(out or p/'data'/'GF10_MERIT_HYDRO_16_BANDS.parquet');dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():raise FileExistsError('Never overwrite scientific extraction release')
 merged.to_parquet(dest,index=False)
 report={'status':'COMPLETE_MERIT_SCIENTIFIC_QC_ALL_GF10' if not missing else 'PARTIAL_MERIT_NOT_GLOBALLY_COMPLETE',
  'expected_GF10_cells':len(ids),'accepted_GF10_cells':len(got),'missing_GF10_cells':len(missing),
  'seam450_independent_acceptance':seam_file.exists(),'16_frozen_bands':core.BANDS,
  'source_v7_accepted_cells':len(base),'new_v8_accepted_cells':len(output),'output_sha256':core.sha(dest)}
 core.write_json(dest.with_suffix('.qc.json'),report)
 return report
