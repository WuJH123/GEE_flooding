"""CPU-bound fast GF10 aligned-window raster reducer.

IMPORTANT: A 1 km resampled working grid is an APPROXIMATION of original
pixel / coast intersections; 'raster-fast' is not exact native pixel area.
For exact source resolution use 'raster-exact' C++ exactextract on a pilot,
then compare area/means and gate accuracy before publication.
"""
from __future__ import annotations
import concurrent.futures,os,time
from pathlib import Path
import numpy as np
import pandas as pd
from rasterio import open as rio_open, band
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.transform import Affine
from .core import file_identity, read_json, json_write, safe_hash

# Explicitly approved native data representations and locked epoch.
PROFILES={
    'ghsl_built_2000':dict(column='built_area_km2_2000',kind='pixel_m2',epoch='2000',source_family='GHSL_BUILT_S_R2023A',source_pixel_area_m2=1_000_000),
    'ghsl_built_2020':dict(column='built_area_km2_2020',kind='pixel_m2',epoch='2020',source_family='GHSL_BUILT_S_R2023A',source_pixel_area_m2=1_000_000),
    'ghsl_nres_2020':dict(column='built_nres_area_km2_2020',kind='pixel_m2',epoch='2020',source_family='GHSL_BUILT_S_NRES_R2023A',source_pixel_area_m2=1_000_000),
    'ghsl_pop_2020':dict(column='population_count_2020',kind='pixel_count',epoch='2020',source_family='GHSL_POP_R2023A',source_pixel_area_m2=1_000_000),
    'ghsl_smod_2020':dict(column='smod_2020',kind='classes',epoch='2020',source_family='GHSL_SMOD_R2023A_V2-0',classes=[10,11,12,13,21,22,23,30]),
    'gmted_elevation':dict(column='elevation_gmted_source_m',kind='mean',epoch='static',source_family='GMTED2010_DERIVED',unit='m'),
    'gmted_slope':dict(column='slope_gmted_unverified_unit',kind='mean',epoch='static',source_family='GMTED2010_DERIVED',unit='UNVERIFIED'),
    'gmted_roughness':dict(column='roughness_gmted_unverified_unit',kind='mean',epoch='static',source_family='GMTED2010_DERIVED',unit='UNVERIFIED'),
    'gmted_tpi':dict(column='tpi_gmted_unverified_unit',kind='mean',epoch='static',source_family='GMTED2010_DERIVED',unit='UNVERIFIED'),
    'gmted_tri':dict(column='tri_gmted_unverified_unit',kind='mean',epoch='static',source_family='GMTED2010_DERIVED',unit='UNVERIFIED'),
    'grip_density':dict(column='road_density_grip4_m_per_km2',kind='mean',epoch='source_static',source_family='GRIP4_DENSITY_5ARCMIN',unit='m/km2'),
    'worldclim_bio1':dict(column='worldclim_bio1_source',kind='mean',epoch='1970-2000',source_family='WORLDCLIM2.1_30s',unit='native_unverified'),
    'worldclim_bio12':dict(column='worldclim_bio12_source',kind='mean',epoch='1970-2000',source_family='WORLDCLIM2.1_30s',unit='mm'),
    'worldclim_bio15':dict(column='worldclim_bio15_source',kind='mean',epoch='1970-2000',source_family='WORLDCLIM2.1_30s',unit='native_unverified'),
    'worldclim_bio18':dict(column='worldclim_bio18_source',kind='mean',epoch='1970-2000',source_family='WORLDCLIM2.1_30s',unit='mm'),
    'worldclim_bio19':dict(column='worldclim_bio19_source',kind='mean',epoch='1970-2000',source_family='WORLDCLIM2.1_30s',unit='mm'),
    'gisd2020_fraction_1km':dict(column='impervious_fraction_2020_proxy',kind='mean',epoch='2020',source_family='GISD30_BINARY_DOWNSAMPLED',unit='fraction'),
    'gisd2000_fraction_1km':dict(column='impervious_fraction_2000_proxy',kind='mean',epoch='2000',source_family='GISD30_BINARY_DOWNSAMPLED',unit='fraction'),
}


def _source_descriptors(paths):
    results=[]
    for p in paths:
        pp=Path(p)
        if not pp.is_file():raise FileNotFoundError(pp)
        with rio_open(p) as s:
            if s.crs is None:raise ValueError(f'Raster CRS missing: {p}')
            if s.count<1:raise ValueError('Raster missing band')
            if abs(s.transform.b)>1e-9 or abs(s.transform.d)>1e-9:
                raise ValueError('Rotated TIFF must be handled separately')
            desc={'file':file_identity(pp),'src_crs':str(s.crs),
                  'resolution':list(s.res),'bounds':list(s.bounds),
                  'nodata':s.nodata,'dtype':s.dtypes[0]}
            try:
                b=transform_bounds(s.crs,'EPSG:6933',*s.bounds,densify_pts=51)
                if any(not np.isfinite(z) for z in b):raise ValueError('nonfinite')
                # Conservative 5km guard for target cell overlap
                desc['bbox_6933']=[b[0]-5000,b[1]-5000,b[2]+5000,b[3]+5000]
            except Exception:desc['bbox_6933']=None
            results.append(desc)
    return results

def _candidate(tile_x,tile_y,side,desc):
    bb=desc['bbox_6933']
    if bb is None:return True
    xa=tile_x*side*10000;ya=tile_y*side*10000
    xb=xa+side*10000;yb=ya+side*10000
    return xa<bb[2] and xb>bb[0] and ya<bb[3] and yb>bb[1]

def _warp(source,tx,ty,side,factor,gdal_threads,kind):
    import rasterio
    n=side*factor
    cellres=10000/factor
    dest=np.full((n,n),np.nan,dtype=np.float32)
    t=Affine(cellres,0,tx*side*10000,0,-cellres,(ty+1)*side*10000)
    with rasterio.Env(GDAL_CACHEMAX=128,GDAL_NUM_THREADS=str(gdal_threads)):
        with rio_open(source) as ds:
            if kind in ('pixel_m2','pixel_count'):
                # Source counts are already integrated within each native
                # 1000m Mollweide pixel; target same 1000m equal-area pixel.
                native=str(ds.crs).upper()
                proj4=ds.crs.to_proj4()
                if (not ds.crs.is_projected or
                    not (('MOLL' in native) or ('54009' in native) or ('+proj=moll' in proj4)) or
                    not all(abs(r-1000)<1e-4 for r in ds.res)):
                    raise ValueError('GHSL per-pixel totals must be verified native 1000m equal-area sources')
                how=Resampling.average
            elif kind=='classes':how=Resampling.nearest
            else:how=Resampling.average
            reproject(source=band(ds,1),destination=dest,
                      dst_transform=t,dst_crs='EPSG:6933',dst_nodata=np.nan,
                      resampling=how,num_threads=gdal_threads,
                      init_dest_nodata=True,warp_mem_limit=128)
    return dest

def _aggregate_1km(values,kind,classes,side,factor):
    if values.shape!=(side*factor,side*factor):raise ValueError('Wrong aligned destination raster')
    a=values.reshape(side,factor,side,factor)
    good=np.isfinite(a)
    valid=good.sum(axis=(1,3)).astype(np.float32)
    cnt=factor*factor
    cov=valid/cnt
    output={}
    if kind=='classes':
        for cl in classes:
            # Values are nearest-neighbour categorical membership, not
            # falsely interpolated numeric SMOD class codes.
            counts=(a==cl).sum(axis=(1,3))
            output[str(cl)]=(counts/cnt).astype(np.float32)
    else:
        numerator=np.where(good,a,0).sum(axis=(1,3))
        if kind=='pixel_m2':out=numerator*(cell_area_m2(factor)/1_000_000) / 1_000_000
        elif kind=='pixel_count':out=numerator*(cell_area_m2(factor)/1_000_000)
        else:out=np.divide(numerator,valid,where=valid>0,out=np.full(valid.shape,np.nan,dtype=np.float32))
        out=np.where(valid>0,out,np.nan)
        output['value']=out.astype(np.float32)
    return output,cov

def cell_area_m2(factor):return float((10000/factor)**2)

def _run_tile(item):
    tilefile,tx,ty,side,paths,profile,output,job_id,factor,threads=item
    p=Path(output)/'tiles'/Path(tilefile).name
    q=p.with_suffix('.qc.json')
    if p.is_file() and q.is_file():
        old=read_json(q)
        if old.get('job_id')==job_id and old.get('status')=='OK' and old.get('n')==len(pd.read_parquet(tilefile,columns=['grid_id'])):
            return {'file':str(p),'status':'REUSED','n':old['n'],'valid':old.get('valid',0)}
        raise FileExistsError('Previous output different or incomplete: '+str(p))
    if p.exists() or q.exists():raise FileExistsError('Previous interrupted output, quarantine and use new job tag: '+str(p))
    g=pd.read_parquet(tilefile,columns=['grid_id','grid_x','grid_y','land_area_km2'])
    r=(ty+1)*side-1-g.grid_y.to_numpy(dtype=int)
    c=g.grid_x.to_numpy(dtype=int)-tx*side
    if (r<0).any() or (c<0).any() or (r>=side).any() or (c>=side).any():
        raise ValueError('GF10 tile coordinates not aligned')
    classes=profile.get('classes',[])
    kind=profile['kind']
    sums={str(k):np.zeros(len(g),dtype=np.float64) for k in (classes if kind=='classes' else ['value'])}
    values_mask=np.zeros(len(g),dtype=bool)
    cv_max=np.zeros(len(g),dtype=np.float32)
    # Multi-source mosaic: for overlapping source tiles, accept first and
    # independently assert agreement on valid-overlap portions.
    disagreements=0;seen=[]
    for src in paths:
        warped=_warp(src,tx,ty,side,factor,threads,kind)
        vals,cov=_aggregate_1km(warped,kind,classes,side,factor)
        cover=cov[r,c]
        avail=cover>0
        if not np.any(avail):continue
        overlap=values_mask&avail
        for k,v in vals.items():
            piece=v[r,c]
            if np.any(overlap):
                mismatch=np.abs(sums[k][overlap]-piece[overlap])
                threshold=.02 if kind in ('classes','mean') else np.maximum(1e-3,np.abs(sums[k][overlap])*.05)
                disagreements+=int(np.count_nonzero(mismatch>threshold))
            fresh=~values_mask&avail
            sums[k][fresh]=piece[fresh]
        cv_max[~values_mask&avail]=cover[~values_mask&avail]
        values_mask|=avail
        seen.append(str(src))
    if disagreements:raise ValueError(f'Overlapping rasters disagree ({disagreements} cells), source footprints may overlap')
    result=g[['grid_id','land_area_km2']].copy()
    if kind=='classes':
        for k,v in sums.items():
            result[f"{profile['column']}_class_{k}_full_cell_fraction"]=np.where(values_mask,v,np.nan).astype(np.float32)
        # official GHSL urban classes; denominator full 100km²
        if profile['column']=='smod_2020':
            urb=sum(sums.get(str(c),0) for c in (21,22,23,30))
            result['smod_urban_fraction_2020_full_cell']=np.where(values_mask,urb,np.nan).astype(np.float32)
    else:
        result[profile['column']]=np.where(values_mask,sums['value'],np.nan).astype(np.float32)
        if kind=='pixel_m2':
            result[profile['column'].replace('area_km2','fraction_full_cell')]=np.where(values_mask,sums['value']/100,np.nan).astype(np.float32)
    if kind=='pixel_m2':
        result[f"{profile['column']}_greater_than_land_area_flag"]=np.where(
            values_mask,sums['value']>g.land_area_km2.to_numpy()+0.05,False)
    result[f"{profile['column']}_valid_sample_fraction"]=cv_max
    result[f"{profile['column']}_coast_approximation_flag"]=(g.land_area_km2.to_numpy()<99.99)
    if kind=='pixel_m2' and (result[profile['column']].dropna()>100.5).any():
        raise ValueError('GHSL built km2 exceeds 100; verify native pixel area and band')
    if kind=='pixel_count' and (result[profile['column']].dropna()<0).any():
        raise ValueError('Population count negative')
    if kind=='mean' and profile['column'].startswith('impervious'):
        observed=result[profile['column']].dropna()
        if not observed.between(0,1.01).all():raise ValueError('Binary GISD fraction must be between 0 and 1')
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.parquet.writing')
    result.to_parquet(tmp,index=False,compression='zstd')
    os.replace(tmp,p)
    json_write(q,{'status':'OK','job_id':job_id,'n':len(g),'valid':int(values_mask.sum()),
                  'sources':seen,'method':'aligned_1km_GDAL_warp_fast_approx',
                  'land_polygon_clipped':False,'source_epoch':profile['epoch'],
                  'source_family':profile['source_family']})
    return {'file':str(p),'status':'WROTE','n':len(g),'valid':int(values_mask.sum())}

def run(tile_root,source_files,profile_name,out,workers=24,gdal_threads=2,
        factor=10,max_tiles=None):
    if profile_name not in PROFILES:raise KeyError(f'Unknown profile: {profile_name}')
    if not 1<=workers<=48 or not 1<=gdal_threads<=4 or workers*gdal_threads>96:
        raise ValueError('96 logical CPU threads maximum; default 24x2; benchmark before 32x2')
    if factor!=10:
        raise ValueError('Only 1km GF10-aligned target (10 subcells per 10km) is validated in v2')
    root=Path(tile_root); tiles=sorted((root/'tiles').glob('tile_*.parquet'))
    if not tiles:raise ValueError('run --tiles to create complete index')
    audit=read_json(root/'tile_index_qc.json')
    paths=[str(Path(x).resolve()) for x in source_files]
    if not paths:raise ValueError('No raster sources')
    desc=_source_descriptors(paths)
    p=PROFILES[profile_name]
    metadata={'schema':'hpc_raster_v2','grid_id':audit['grid_sha256'],
              'profile':profile_name,'factor':factor,'files':desc}
    jobid=safe_hash(metadata)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    manifest=out/'job.json'
    if manifest.exists():
        if read_json(manifest)['job_id']!=jobid:raise ValueError('Output directory belongs to different sources/profile')
    else:
        if (out/'tiles').exists() and any((out/'tiles').iterdir()):
            raise ValueError('Preexisting tiles without a job manifest')
        json_write(manifest,{'job_id':jobid,'metadata':metadata,'status':'IN_PROGRESS'})
    idx=pd.read_parquet(root/'index.parquet')
    available={z['tile_file']:(int(z['tile_x']),int(z['tile_y'])) for _,z in idx.iterrows()}
    if set(available)!=set(x.name for x in tiles):raise ValueError('Tile index incomplete or changed')
    if max_tiles:
        # A geographically distributed test avoids benchmarking only the
        # westernmost/southernmost tiles in lexicographic order.
        picks=np.linspace(0,len(tiles)-1,min(int(max_tiles),len(tiles)),dtype=int)
        selected=[tiles[k] for k in sorted(set(picks))]
    else:selected=tiles
    tasks=[]
    for tile in selected:
        tx,ty=available[tile.name]
        candidates=[paths[i] for i,d in enumerate(desc) if _candidate(tx,ty,audit['tile_size'],d)]
        tasks.append((str(tile),tx,ty,audit['tile_size'],candidates,p,str(out),jobid,factor,gdal_threads))
    start=time.perf_counter();stats=[]
    # Rasterio/GDAL's C warp releases the Python GIL; separate dataset
    # instances are opened per worker. Thread pool avoids 32 copies of all
    # raster metadata/data and Windows spawn overhead of ProcessPool.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(_run_tile,t):t[0] for t in tasks}
        for i,f in enumerate(concurrent.futures.as_completed(futs),1):
            stats.append(f.result())
            if i==1 or i%25==0 or i==len(tasks):
                print(f'[raster] {i}/{len(tasks)} tiles, processed {sum(z["status"]=="WROTE" for z in stats)}',flush=True)
    seconds=time.perf_counter()-start
    qc={'status':'PILOT_PARTIAL' if max_tiles else 'ALL_TILES_FAST_APPROX_NEEDS_EXACT_AND_COAST_QA',
        'n_tasks':len(tasks),'n_reused':sum(z['status']=='REUSED' for z in stats),
        'n_written':sum(z['status']=='WROTE' for z in stats),
        'valid_rows':sum(z.get('valid',0) for z in stats),
        'elapsed_s':seconds,'tiles_per_second':len(tasks)/max(seconds,.0001),
        'job_id':jobid,'profile':profile_name,'workers':workers,'gdal_threads_per_worker':gdal_threads,
        'source_epoch':p['epoch'],'native_source':p['source_family'],
        'method':'GDAL_aligned_1km_resample_NOT_EXACT_AREA',
        'land_polygon_clipped':False,'publication_ready':False}
    json_write(out/'run_qc.json',qc)
    return qc
