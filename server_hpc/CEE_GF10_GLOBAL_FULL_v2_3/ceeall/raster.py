"""ExactExtract source-resolution aggregation to 10km polygons, with provenance.

Raster mean values are native source units until a separately checked source
unit conversion is specified. This is NOT a land-polygon-masked statistic.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import re
from concurrent.futures import ProcessPoolExecutor,as_completed
from .common import fidentity,ensure_job,atomic_json,atomic_parquet,read_json
from .common import gf10_bounds

PROFILES={
 'gmted': {'kind':'mean','scope':'static','allowed':['elevation_','slope_','roughness_','tpi_','tri_'],
           'unit':'ORIGINAL_MEAN_STATISTIC_UNIT_CHECKED_PER_LAYER'},
 'worldclim-bio':{'kind':'mean','scope':'1970-2000','allowed':['wc2.1_30s_bio_'],
          'unit':'SOURCE_NATIVE_VERIFY_SCALE'},
 'worldclim-monthly':{'kind':'mean','scope':'1970-2000',
         'allowed':['wc2.1_30s_prec_','wc2.1_30s_tavg_','wc2.1_30s_tmin_',
          'wc2.1_30s_tmax_','wc2.1_30s_srad_','wc2.1_30s_vapr_','wc2.1_30s_wind_'],
         'unit':'SOURCE_NATIVE_VERIFY_SCALE'},
 'grip-density':{'kind':'mean','scope':'GRIP4_static','allowed':['grip4_total_dens_'],
         'unit':'m_per_km2_native_5arcmin'},
}

def candidates(root,profile):
    root=Path(root); raw=root/'CEE数据'; staged=root/'data/staged/cee_all'
    if profile not in PROFILES:raise KeyError(profile)
    patterns=PROFILES[profile]['allowed']
    paths=[]
    for folder in (raw,staged):
        if folder.is_dir():
            for p in folder.rglob('*'):
                if p.suffix.lower() not in ('.tif','.tiff','.asc'):continue
                if any(p.name.lower().startswith(pre) for pre in patterns):paths.append(p)
    return sorted(set(paths))



def ensure_grip4_georeference(root, source, profile):
    """Fix ONLY official GRIP4 worldwide 5' AAIGrid lacking its WGS84 PRJ.

    Adds a sidecar to the *staged extraction*, never changes source ASCII values
    or any original download, and never assumes a missing CRS for other inputs.
    The strict global geometry contract is checked before assigning EPSG:4326.
    """
    if profile != 'grip-density':
        return None
    import rasterio
    from pyproj import CRS
    from .common import sha256
    root=Path(root).resolve()
    source=Path(source).resolve()
    expected=root/'data/staged/cee_all/GRIP4_density_total/grip4_total_dens_m_km2.asc'
    if source != expected:
        raise ValueError('GRIP4 CRS fix restricted to official staged total-density file: '+str(source))
    if not source.is_file():
        raise FileNotFoundError(source)

    def metadata():
        with rasterio.open(source) as src:
            if src.driver != 'AAIGrid' or src.count != 1 or src.transform.is_identity:
                raise ValueError('GRIP4 invalid ASCII Grid driver, band count or affine transform')
            if src.width != 4320 or src.height != 2160:
                raise ValueError(f'GRIP4 wrong global dimensions {(src.width,src.height)}; expected 4320x2160')
            ext=tuple(float(v) for v in src.bounds)
            if any(abs(a-b)>0.00005 for a,b in zip(ext,(-180.0,-90.0,180.0,90.0))):
                raise ValueError('GRIP4 world extent mismatch (cannot assign WGS84): '+str(ext))
            resolution=tuple(abs(float(v)) for v in src.res)
            if any(abs(a-1/12)>1e-7 for a in resolution):
                raise ValueError('GRIP4 resolution is not 5 arcminutes: '+str(resolution))
            if src.crs and not CRS.from_user_input(src.crs).equals(CRS.from_epsg(4326),ignore_axis_order=True):
                raise ValueError('GRIP4 already has an unexpected CRS, no override: '+str(src.crs))
            return dict(driver=src.driver,width=src.width,height=src.height,
                        bounds=ext,resolution=resolution,crs=str(src.crs) if src.crs else None,
                        nodata=src.nodata,dtype=src.dtypes[0])
    before=metadata()
    prj=source.with_suffix('.prj')
    created=False
    if before['crs'] is None:
        if prj.exists():
            raise ValueError('GRIP4 sidecar exists but Rasterio cannot read its CRS; manual audit required: '+str(prj))
        # GDAL AAIGrid reads coordinate system from a same-stem .prj file.
        # Use an ESRI-compatible WKT1 representation, not a guessed GeoTIFF.
        content=CRS.from_epsg(4326).to_wkt(version='WKT1_ESRI')+'\n'
        temp=prj.with_name(prj.name+'.writing')
        if temp.exists():raise FileExistsError('Incomplete GRIP4 PRJ sidecar from prior attempt: '+str(temp))
        try:
            with temp.open('x',encoding='utf-8',newline='\n') as fp:
                fp.write(content)
            # Do not overwrite an existing PRJ created by another process.
            if prj.exists():raise FileExistsError('Concurrent GRIP4 PRJ writer detected: '+str(prj))
            import os
            os.replace(temp,prj)
            created=True
        finally:
            if temp.exists():temp.unlink()
    after=metadata()
    if after['crs'] is None:
        raise ValueError('GRIP4 WGS84 .prj was written but GDAL did not recognize it; stop and inspect')
    report={'status':'GRIP4_WGS84_5ARCMIN_NATIVE_COORDINATES_VERIFIED',
            'provenance':'PBL/GLOBIO GRIP4 official global total density ASCII Grid 5arcminute',
            'method':'WKT1_ESRI sidecar only, no resampling; original ASCII data unmodified',
            'units':'m/km2','source':str(source),'original_data_mutated':False,
            'sidecar_created':created,'prj_path':str(prj),
            'prj_sha256':sha256(prj),'metadata_before':before,'metadata_after':after,
            'scientific_note':'5 arcminute road density is a coarse original-data proxy, not 10km vector-exact road length',
            'publication_ready':False}
    from .common import atomic_json
    audit=root/'reports/cee_full_v2/grip4_ascii_crs_audit_v23.json'
    atomic_json(audit,report)
    return report


def _build_polygons(df,crs):
    import geopandas as gpd
    from shapely.geometry import box
    # Densify at original equal-area EPSG:6933 before transforming to native
    # geographic CRS. Straight EPSG:6933 edges are not straight lat/lon edges.
    from shapely import segmentize
    polys=[segmentize(box(*gf10_bounds(x,y)),2000) for x,y in zip(df.grid_x,df.grid_y)]
    frame=gpd.GeoDataFrame({'grid_id':df.grid_id.to_numpy()},geometry=polys,crs='EPSG:6933')
    if str(frame.crs)!=str(crs):frame=frame.to_crs(crs)
    # Antimeridian warp can generate world-spanning polygons. Preserve explicit NA.
    if frame.crs.is_geographic:
        bad=(frame.bounds.maxx-frame.bounds.minx)>5
        if bad.any():frame.loc[bad,'geometry']=None
    return frame

def _one(task):
    tile,source,profile,out,jid=task
    import pandas as pd
    import geopandas as gpd
    import rasterio
    from exactextract import exact_extract
    tile=Path(tile);source=Path(source);out=Path(out)
    dst=out/'tiles'/tile.name;qc=dst.with_suffix('.qc.json')
    if dst.exists() or qc.exists():
        if not dst.exists() or not qc.exists():raise FileExistsError('Orphan/partial output, manual audit required: '+str(dst))
        meta=read_json(qc)
        if meta.get('job_id')!=jid or meta.get('status')!='OK':raise FileExistsError('Fingerprint/QC conflict: '+str(dst))
        import pyarrow.parquet as pq
        if pq.ParquetFile(dst).metadata.num_rows!=meta['rows']:raise ValueError('Row count differs '+str(dst))
        return ('REUSED',len(pd.read_parquet(tile,columns=['grid_id'])),meta.get('valid_rows',0))
    df=pd.read_parquet(tile)
    if df.grid_id.duplicated().any():raise ValueError('Duplicate ID in tile '+str(tile))
    with rasterio.open(source) as src:
        if not src.crs or src.count!=1 or src.transform.is_identity:raise ValueError('Missing source georeference '+str(source))
        if profile.startswith('worldclim') and not src.crs.is_geographic:raise ValueError('WorldClim should be geographic 30sec')
        if profile=='grip-density' and not src.crs.is_geographic:raise ValueError('GRIP native density is geographic 5arcmin')
        # Reuse exactly the same densified GF10 geometry across the 103
        # independent WorldClim rasters; avoids millions of repeat PROJ calls.
        cache=Path(tile).parents[2]/'cee_geo4326_v2'/Path(tile).name
        if src.crs.is_geographic and (str(src.crs)=='EPSG:4326' or (profile=='grip-density' and str(src.crs)=='OGC:CRS84')) and cache.is_file():
            g=gpd.read_parquet(cache)
            if len(g)!=len(df) or not np.array_equal(g.grid_id.to_numpy(),df.grid_id.to_numpy()):
                raise ValueError('Cached source polygons out of sync with GF10 frozen IDs')
        else:g=_build_polygons(df,src.crs)
        good=g.geometry.notna() & ~g.geometry.is_empty
        if good.any():
            ops=['count','mean(coverage_weight=area_spherical_m2)'] if src.crs.is_geographic else ['count','mean']
            temp=exact_extract(str(source),g.loc[good],ops,include_cols=['grid_id'],output='pandas')
            if len(temp)!=int(good.sum()):
                raise ValueError('ExactExtract native geometry row count mismatch')
        else:
            # Unsupported antimeridian warp stays NaN, never becomes a zero.
            temp=pd.DataFrame(columns=['grid_id','count','mean'])
    if temp.grid_id.duplicated().any():raise ValueError('Extraction produced duplicate ID')
    data=df[['grid_id']].merge(temp,on='grid_id',how='left',validate='one_to_one',sort=False)
    name=re.sub('[^a-zA-Z0-9_]+','_',source.stem).lower()
    if profile=='gmted':
        # User-verified downloaded products are mean-statistic terrain layers.
        # Use a stable variable name rather than the ambiguous 'GMTEDmn/md'
        # filename suffix. Local GeoTIFF descriptions still require audit.
        kind=next((x for x in ('elevation','slope','roughness','tpi','tri')
                   if source.stem.lower().startswith(x+'_')),None)
        if kind is None:raise ValueError('Unknown GMTED mean product '+str(source))
        name='gmted_mean_'+kind
    value_col=next(c for c in temp.columns if c.startswith('mean'))
    data=data.rename(columns={value_col:f'{name}_mean_native','count':f'{name}_native_valid_pixel_count'})
    val_col=f'{name}_mean_native'
    nvalid=int(pd.to_numeric(data[val_col],errors='coerce').notna().sum())
    if (data[f'{name}_native_valid_pixel_count']<0).any():raise ValueError('Negative pixel count')
    atomic_parquet(data,dst)
    source_description=''
    if profile=='gmted':
        with rasterio.open(source) as check:
            source_description=' '.join([str(x) for x in check.descriptions if x] +
                [str(x) for x in check.tags().values() if isinstance(x,str)])
    desc_conflict=(profile=='gmted' and
                   ('maximum statistic' in source_description.lower() or
                    'minimum statistic' in source_description.lower()))
    atomic_json(qc,{'status':'OK','job_id':jid,'rows':len(data),'valid_rows':nvalid,
                    'gmted_download_statistic':'MEAN_USER_CONFIRMED' if profile=='gmted' else None,
                    'gmted_native_metadata_conflict':bool(desc_conflict),
                    'gmted_description_excerpt':source_description[:500] if profile=='gmted' else None,
                    'source':str(source),'native_units_not_converted':True,
                    'not_land_polygon_clipped':True,'geographic_area_weighted':True,'n_failed_geometries':int((~good).sum()),'not_independent_product_unit_validation':True})
    return ('WROTE',len(data),nvalid)

def run(root,profile,source,workers=8,max_tiles=12,output=None):
    root=Path(root);source=Path(source)
    if workers<1 or workers>32:raise ValueError('Workers 1-32; benchmark first')
    if not source.exists():raise FileNotFoundError(source)
    # AAIGrid has an affine transform but often no accompanying projection.
    # Correct only this official, verified GRIP4 product before workers spawn.
    grip_audit=ensure_grip4_georeference(root,source,profile)
    tile_root=root/'data/working/cee_all_tiles64_v11/tiles'
    tiles=sorted(tile_root.glob('tile_*.parquet'))
    if not tiles:raise FileNotFoundError('Run grid-tiles first')
    if max_tiles is not None:tiles=tiles[:max_tiles]
    out=Path(output or (root/'data/derived/cee_all_v11'/profile/source.stem))
    spec={'source':fidentity(source),'profile':profile,'method':'native_exactextract_v11',
          'source_unit':PROFILES[profile]['unit'],'tile_size':64,
          'grid_file':fidentity(root/'gf10_global_nonantarctic_land.parquet')}
    # IMPORTANT: do not alter v2.2 job fingerprint: its failed GRIP4 run
    # already created job.json before the missing-CRS exception. Preserve it.
    jid=ensure_job(out,spec)
    tasks=[(str(p),str(source),profile,str(out),jid) for p in tiles]
    results=[]
    if workers==1:
        for task in tasks:results.append(_one(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(_one,t) for t in tasks]
            for f in as_completed(futures):results.append(f.result())
    counts={s:sum(x[0]==s for x in results) for s in ('REUSED','WROTE')}
    status='FULL_TILES_NATIVE_EXACT_NEEDS_LAND_QA' if max_tiles is None else 'PILOT_PARTIAL'
    qc={'status':status,'profile':profile,'source':str(source),'workers':workers,
        'n_tasks':len(tasks),'n_reused':counts['REUSED'],'n_written':counts['WROTE'],
        'n_rows':sum(x[1] for x in results),'n_valid_rows':sum(x[2] for x in results),
        'grip4_projection_sidecar_sha256':grip_audit['prj_sha256'] if grip_audit else None,
        'not_land_polygon_clipped':True,'publication_ready':False,'job_id':jid,'statistic_contract':'GMTED mean; GF10 native-pixel area-weighted mean' if profile=='gmted' else 'native source mean'}
    atomic_json(out/'run_qc.json',qc)
    return qc
