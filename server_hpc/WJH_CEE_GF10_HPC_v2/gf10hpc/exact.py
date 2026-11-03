"""High-accuracy GF10 native-pixel C++ exactextract, tile + process parallel.

Input polygons are full 10 km EPSG6933 boxes. Source pixels are evaluated
at native resolution with their fractional overlap. For geographic source
continuous means use spherical area weights; coastline land-only masks are
NOT available in the frozen GF10 file and remain a distinct QA task.
"""
from __future__ import annotations
import concurrent.futures,os,time
from pathlib import Path
import numpy as np
import pandas as pd
from .core import safe_hash,read_json,json_write
from .raster import PROFILES,_source_descriptors,_candidate


def _exact_one(job):
    tilefile,tx,ty,side,sources,profile,out,jobid=job
    import geopandas as gpd
    import rasterio
    from shapely.geometry import box
    from exactextract import exact_extract
    tile=Path(tilefile);output=Path(out)/'tiles'/tile.name
    qc=output.with_suffix('.qc.json')
    g=pd.read_parquet(tile,columns=['grid_id','grid_x','grid_y','land_area_km2'])
    if output.exists() and qc.exists():
        old=read_json(qc)
        if old.get('job_id')==jobid and old.get('status')=='OK' and old.get('n')==len(g):
            return {'status':'REUSED','valid':old['valid'],'n':len(g)}
        raise FileExistsError('Existing output mismatched '+str(output))
    if output.exists() or qc.exists():raise FileExistsError('Interrupted output; choose new versioned tag')
    boxes=[box(x*10000,y*10000,(x+1)*10000,(y+1)*10000) for x,y in zip(g.grid_x,g.grid_y)]
    zones=gpd.GeoDataFrame({'grid_id':g.grid_id.astype(str).values},
                            geometry=boxes,crs='EPSG:6933')
    cols=profile['column'];kind=profile['kind'];classes=profile.get('classes',[])
    raw={str(k):np.full(len(g),np.nan,np.float64) for k in (classes if kind=='classes' else ['value'])}
    counts=np.zeros(len(g),float)
    present=np.zeros(len(g),dtype=bool)
    for source in sources:
        with rasterio.open(source) as src:
            if src.crs is None:raise ValueError('Missing CRS')
            if kind in ('pixel_m2','pixel_count'):
                if not src.crs.is_projected or not all(abs(r-1000)<1e-4 for r in src.res):
                    raise ValueError('Native GHSL counts require source 1000m equal-area grid')
                st=str(src.crs).upper();proj=src.crs.to_proj4()
                if not ('54009' in st or 'MOLL' in st or '+proj=moll' in proj):
                    raise ValueError('Only audited JRC Mollweide GHSL totals supported')
            z=zones.to_crs(src.crs)
            # Use source geometry, never fabricate raster category fractions.
            ops=['count','frac'] if kind=='classes' else (
                ['count','mean(coverage_weight=area_spherical_m2)']
                if kind=='mean' and src.crs.is_geographic else
                ['count','mean'] if kind=='mean' else ['count','sum'])
            value=exact_extract(source,z,ops,include_cols=['grid_id'],
                                output='pandas',
                                output_options={'frac_as_map':True} if kind=='classes' else None)
            value.grid_id=value.grid_id.astype(str)
            if value.grid_id.duplicated().any():raise ValueError('Repeated GF10 from one TIFF')
            value=g[['grid_id']].merge(value,on='grid_id',how='left',validate='one_to_one')
            w=pd.to_numeric(value['count'],errors='coerce').fillna(0).to_numpy()
            valid=w>0
            overlap=valid&present
            if np.any(overlap):
                raise ValueError('Multiple source native GeoTIFFs intersect same GF10; deduplicate source tiles explicitly')
            if kind=='classes':
                for i,clmap in enumerate(value['frac']):
                    if not valid[i]:continue
                    if not isinstance(clmap,dict):raise ValueError('Expected frac_as_map dictionary')
                    # Source native pixels 1000m, fraction of whole GF10
                    for c in classes:
                        raw[str(c)][i]=float(clmap.get(c,clmap.get(str(c),0)))*w[i]/100.0
            else:
                col='sum' if kind in ('pixel_m2','pixel_count') else [k for k in value if 'mean' in k][0]
                v=pd.to_numeric(value[col],errors='coerce').to_numpy(dtype=float)
                if kind=='pixel_m2':v/=1e6
                raw['value'][valid]=v[valid]
            counts[valid]=w[valid]
            present |=valid
    result=g[['grid_id','land_area_km2']].copy()
    if kind=='classes':
        for cl in classes:
            result[f'{cols}_class_{cl}_full_cell_fraction']=raw[str(cl)].astype(np.float32)
        if cols=='smod_2020':
            urban=sum(np.nan_to_num(raw[str(cl)],nan=0.) for cl in (21,22,23,30))
            result['smod_urban_fraction_2020_full_cell']=np.where(present,urban,np.nan).astype(np.float32)
    else:
        result[cols]=raw['value'].astype(np.float32)
        if kind=='pixel_m2':result[cols.replace('area_km2','fraction_full_cell')]=(raw['value']/100).astype(np.float32)
    # count in native source pixels is physically meaningful only for 1km equal-area source.
    if kind=='pixel_m2':
        result[f'{cols}_greater_than_land_area_flag']=np.where(
            present,raw['value']>g.land_area_km2.to_numpy()+.05,False)
    result[f'{cols}_native_valid_coverage']=np.where(present,np.minimum(counts/100.,1),0).astype('float32') if kind in ('pixel_m2','pixel_count','classes') else np.where(present,1.,0).astype('float32')
    result[f'{cols}_coast_approximation_flag']=g.land_area_km2.to_numpy()<99.99
    if kind=='pixel_m2' and (result[cols].dropna()>100.1).any():raise ValueError('GHSL built area exceeds a 10km cell')
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix('.writing.parquet')
    result.to_parquet(tmp,index=False,compression='zstd')
    os.replace(tmp,output)
    json_write(qc,{'status':'OK','job_id':jobid,'n':len(g),'valid':int(present.sum()),
        'method':'C++_exactextract_source_native_coverage',
        'source_epoch':profile['epoch'],'native_CRS_area_weights':True,
        'land_polygon_clipped':False})
    return {'status':'WROTE','valid':int(present.sum()),'n':len(g)}

def run(tile_root,source_files,profile_name,out,workers=16,max_tiles=None):
    if profile_name not in PROFILES:raise KeyError(profile_name)
    if not 1<=workers<=32:raise ValueError('Run 8..24 C++ exactextract processes after pilot; memory bound')
    root=Path(tile_root);alltiles=sorted((root/'tiles').glob('tile_*.parquet'))
    audit=read_json(root/'tile_index_qc.json')
    if not alltiles:raise FileNotFoundError('No frozen GF10 tile shards')
    paths=[str(Path(p).resolve()) for p in source_files]
    desc=_source_descriptors(paths)
    metadata={'method':'native_C++','grid_sha':audit['grid_sha256'],
              'source_descriptions':desc,'profile':profile_name}
    jobid=safe_hash(metadata)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    manifest=out/'job.json'
    if manifest.exists():
        if read_json(manifest).get('job_id')!=jobid:raise ValueError('Source/provenance changed')
    else:
        if (out/'tiles').exists() and any((out/'tiles').iterdir()):raise FileExistsError('Orphan output tiles')
        json_write(manifest,{'job_id':jobid,'metadata':metadata})
    index=pd.read_parquet(root/'index.parquet')
    positions={x.tile_file:(int(x.tile_x),int(x.tile_y)) for x in index.itertuples(index=False)}
    if max_tiles:
        picked=np.linspace(0,len(alltiles)-1,min(int(max_tiles),len(alltiles)),dtype=int)
        tiles=[alltiles[i] for i in sorted(set(picked))]
    else:tiles=alltiles
    todo=[]
    for tile in tiles:
        tx,ty=positions[tile.name]
        src=[paths[i] for i,d in enumerate(desc) if _candidate(tx,ty,audit['tile_size'],d)]
        todo.append((str(tile),tx,ty,audit['tile_size'],src,PROFILES[profile_name],str(out),jobid))
    started=time.perf_counter();results=[]
    # Separate Windows processes for C++/GDAL file handles; each process
    # opens only its relevant native raster and one GF10 tile at a time.
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_exact_one,t) for t in todo]
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            results.append(f.result())
            if i%20==0 or i==len(todo):print(f'[native exact] {i}/{len(todo)}',flush=True)
    qa={'status':'PILOT_PARTIAL' if max_tiles else 'ALL_TILES_NATIVE_EXACT_NEEDS_COAST_QA',
        'n_tasks':len(todo),'n_written':sum(z['status']=='WROTE' for z in results),
        'n_reused':sum(z['status']=='REUSED' for z in results),
        'valid_rows':sum(z['valid'] for z in results),
        'elapsed_s':time.perf_counter()-started,'profile':profile_name,
        'method':'C++ exactextract native weighted pixels',
        'source_epoch':PROFILES[profile_name]['epoch'],
        'native_source':PROFILES[profile_name]['source_family'],
        'source_crs_pixel_coverage_not_global_land_polygon_mask':True,
        'exactextract_fraction_map_api':'frac + output_options.frac_as_map',
        'land_polygon_clipped':False,'publication_ready':False}
    json_write(out/'run_qc.json',qa)
    return qa
