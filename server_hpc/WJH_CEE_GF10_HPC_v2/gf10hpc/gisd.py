"""GISD30 0..8 native 30m class → real binary 2000/2020 fractions.

This stage uses raw EPSG4326 classification images, converts classes to
binary *before* reprojection. The output is EPSG6933 1km fraction COG-like
TIFF and IS APPROXIMATE at coastlines/sub-1km heterogeneous ground.
All source input is checked for known 0..8 classes and retained in QA.
"""
from __future__ import annotations
import concurrent.futures,math,os,time
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject,Resampling,transform_bounds
from .core import json_write,read_json,file_identity

def _one(path,outdir,gdal_threads=2):
    src=Path(path)
    out=Path(outdir)
    out2000=out/'2000'/f'gisd2000_frac_{src.stem}.tif'
    out2020=out/'2020'/f'gisd2020_frac_{src.stem}.tif'
    qc=out/'qc'/f'{src.stem}.json'
    if out2000.exists() and out2020.exists() and qc.exists():
        j=read_json(qc)
        if j.get('source')==file_identity(src) and j.get('status')=='OK':return {'status':'REUSED','file':str(src)}
        raise ValueError('Source changed or old GISD output unaudited; choose new output tag')
    if out2000.exists() or out2020.exists() or qc.exists():
        raise FileExistsError('Partial output; quarantine and use new version tag: '+str(src))
    with rasterio.Env(GDAL_CACHEMAX=96):
        with rasterio.open(src) as ds:
            if str(ds.crs)!='EPSG:4326' or ds.count!=1:
                raise ValueError('GISD30 must be original EPSG:4326, one category band')
            if ds.nodata==0:
                raise ValueError('GISD source metadata uses 0 as nodata, but 0 is pervious. Audit source first.')
            if ds.width>19000 or ds.height>19000:
                raise ValueError('Unexpected GISD30 tile size')
            data=ds.read(1)
            valid=(data>=0)&(data<=8)
            if ds.nodata is not None:valid &= data!=ds.nodata
            seen=np.unique(data)
            if np.any((seen>8)&(seen!=ds.nodata)):
                raise ValueError(f'Unexpected GISD30 category values: {seen}')
            bounds=transform_bounds('EPSG:4326','EPSG:6933',*ds.bounds,densify_pts=41)
            minx=math.floor(bounds[0]/1000)*1000
            miny=math.floor(bounds[1]/1000)*1000
            maxx=math.ceil(bounds[2]/1000)*1000
            maxy=math.ceil(bounds[3]/1000)*1000
            w=int((maxx-minx)/1000);h=int((maxy-miny)/1000)
            if not (0<w<2000 and 0<h<2000):
                raise ValueError('Unexpected 1km projected target tile shape')
            transform=from_origin(minx,maxy,1000,1000)
            dests={}
            for year,limit in ((2000,4),(2020,8)):
                binary=np.where(valid,(data>=1)&(data<=limit),255).astype(np.uint8)
                target=np.full((h,w),-9999,dtype=np.float32)
                reproject(binary,target,src_transform=ds.transform,src_crs=ds.crs,
                          src_nodata=255,dst_transform=transform,dst_crs='EPSG:6933',
                          dst_nodata=-9999,resampling=Resampling.average,num_threads=gdal_threads)
                keep=target!=-9999
                if keep.any() and not np.all((target[keep]>=-1e-5)&(target[keep]<=1.00001)):
                    raise ValueError('GISD binary fraction outside [0,1]')
                dst=out2000 if year==2000 else out2020
                dst.parent.mkdir(parents=True,exist_ok=True)
                tmp=dst.with_name(dst.stem+'.writing.tif')
                with rasterio.open(tmp,'w',driver='GTiff',height=h,width=w,count=1,
                     crs='EPSG:6933',transform=transform,dtype='float32',nodata=-9999,
                     compress='deflate',predictor=3,tiled=True,blockxsize=256,blockysize=256,
                     BIGTIFF='IF_SAFER') as writer:
                    writer.write(target,1)
                    writer.update_tags(source_product='GISD30_1985_2020',
                        source_epoch=str(year),classification='1..4' if year==2000 else '1..8',
                        resampling='native_30m_binary_then_average_to_1km')
                os.replace(tmp,dst)
                dests[year]=str(dst)
    json_write(qc,{'status':'OK','source':file_identity(src),'classes_found':seen.tolist(),
         'count_valid':int(valid.sum()),'outputs':dests,'engine':'binary-before-average',
         'land_polygon_clipped':False,'native_source_m':30,
         'statistical_caveat':'Approximated 1km fractions from native EPSG4326 categorical pixels; small/coastal cells require exact native cross-check'})
    return {'status':'WROTE','file':str(src)}

def run(source_dir,out,workers=8,gdal_threads=2,max_files=None):
    p=Path(source_dir)
    tifs=sorted(p.rglob('GISD30_1985-2020_*.tif'))
    if not tifs:raise FileNotFoundError('No extracted GISD30 native TIFFs at '+str(p))
    if len(tifs)!=len({f.name for f in tifs}):raise ValueError('Duplicate GISD30 tile names from RAR staging')
    if workers>16 or workers*gdal_threads>48:raise ValueError('GISD native 30m tiles need bounded RAM; max 16 workers, 48 threads')
    selected=tifs[:int(max_files)] if max_files else tifs
    started=time.perf_counter();result=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_one,p,out,gdal_threads) for p in selected]
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            result.append(f.result())
            if i%20==0 or i==len(selected):print(f'[GISD] {i}/{len(selected)} native tiles processed',flush=True)
    qc={'status':'PILOT' if max_files else 'GISD_BINARY_1KM_PREPARATION_COMPLETE_NEEDS_EXACT_QA',
        'tifs_detected':len(tifs),'paper_reference_tile_count_requires_independent_inventory_QA':961,
        'source_inventory_tile_count_note':'count differs from historical public packaging in some copies; inspect actual 5-degree tile coverage',
        'must_audit_coverage_mask_not_assume_full_globe':True,
        'processed':len(selected),
        'written':sum(r['status']=='WROTE' for r in result),'reused':sum(r['status']=='REUSED' for r in result),
        'elapsed_s':time.perf_counter()-started,'output':str(out),
        'publication_ready':False}
    json_write(Path(out)/'run_qc.json',qc)
    return qc
