"""Fail-closed native-source checks; no unreviewed source may become paper data.

Checks metadata against authoritative primary product contracts, not against
invented assumptions based solely on a downloaded filename. Small sampled
windows help detect blatant class/unit errors; they do not prove global totals.
"""
from __future__ import annotations
import math
from pathlib import Path
import rasterio
import numpy as np
from rasterio.windows import Window
from .raster import PROFILES
from .core import json_write,file_identity

GHSL_KINDS={'pixel_m2','pixel_count','classes'}
SMOD_CLASSES={10,11,12,13,21,22,23,30}

# JRC docs: built m² per source pixel, population people per pixel, SMOD V2 class code.
PRIMARY_SOURCES={
 'GHSL_BUILT_S_R2023A':'https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php',
 'GHSL_BUILT_S_NRES_R2023A':'https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php',
 'GHSL_POP_R2023A':'https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php',
 'GHSL_SMOD_R2023A_V2-0':'https://human-settlement.emergency.copernicus.eu/ghs_smod2023.php',
 'WORLDCLIM2.1_30s':'https://www.worldclim.org/data/worldclim21.html',
 'GISD30_BINARY_DOWNSAMPLED':'https://essd.copernicus.org/articles/14/1831/2022/',
 'GMTED2010_DERIVED':'https://www.usgs.gov/coastal-and-marine-geology-program/gmted2010',
 'GRIP4_DENSITY_5ARCMIN':'https://www.globio.info/download-grip-dataset',
}


def _sample(ds):
    # Stratified, bounded random-looking windows; never read all pixels.
    stats=[]
    for fx,fy in ((.16,.24),(.5,.5),(.83,.73)):
        w=min(256,ds.width);h=min(256,ds.height)
        x=max(0,min(ds.width-w,int(ds.width*fx-w/2)))
        y=max(0,min(ds.height-h,int(ds.height*fy-h/2)))
        mask=ds.read(1,window=Window(x,y,w,h),masked=True)
        v=np.asarray(mask.compressed(),dtype=np.float64)
        v=v[np.isfinite(v)]
        if len(v):stats.append(v)
    if not stats:return {'n_sample_valid':0,'min':None,'max':None,'unique':[]}
    values=np.concatenate(stats)
    return {'n_sample_valid':int(values.size),'min':float(values.min()),
            'max':float(values.max()),
            'unique':sorted({int(v) for v in np.unique(values)})[:80] if len(np.unique(values))<80 else [],
            'n_sample_distinct':int(len(np.unique(values)))}


def verify_source(source, profile, out):
    if profile not in PROFILES:raise KeyError(f'Unregistered physical-unit profile: {profile}')
    p=Path(source)
    if not p.is_file():raise FileNotFoundError(p)
    contract=PROFILES[profile]
    kind=contract['kind']
    warnings=[]
    with rasterio.open(p) as ds:
        if ds.count!=1 or not ds.crs:raise ValueError('Expected one band and explicitly georeferenced CRS')
        if abs(ds.transform.b)>1e-9 or abs(ds.transform.d)>1e-9:
            raise ValueError('Rotated rasters require independent audit')
        sample=_sample(ds)
        meta={'source':file_identity(p),'profile':profile,'family':contract['source_family'],
              'data_epoch':contract['epoch'],'physical_unit':contract.get('unit',
                          'm²/native_pixel' if kind=='pixel_m2' else
                          'persons/native_pixel' if kind=='pixel_count' else 'categorical'),
              'crs':str(ds.crs),'resolution':[abs(x) for x in ds.res],
              'bounds':list(ds.bounds),'shape':[ds.height,ds.width],
              'dtype':ds.dtypes[0],'nodata':ds.nodata,'band_description':ds.descriptions[0],
              'band_tags':ds.tags(1),'dataset_tags':ds.tags(),
              'scale':ds.scales[0],'offset':ds.offsets[0],
              'sample':sample,'official_source':PRIMARY_SOURCES.get(contract['source_family']),
              'land_mask_applied':False,'verified_global_range':False}
        if kind in GHSL_KINDS:
            # 1000 m native JRC World Mollweide products; source pixel counts
            # must not be used as densities or multiplied by 1km² a second time.
            proj4=ds.crs.to_proj4()
            if (not ds.crs.is_projected or not ('+proj=moll' in proj4 or
               '54009' in str(ds.crs)) or not all(abs(x-1000)<.0001 for x in ds.res)):
                raise ValueError('This profile requires native 1000m World Mollweide JRC raster')
            if kind=='classes':
                if not np.issubdtype(np.dtype(ds.dtypes[0]),np.integer):
                    raise ValueError('SMOD class codes must be integer, not averaged floats')
                bad=set(sample['unique'])-SMOD_CLASSES
                if bad:raise ValueError('Unrecognized official SMOD v2 classes: '+str(bad))
                if sample['min'] is not None and sample['min']<0:
                    raise ValueError('Negative non-nodata SMOD code sampled; inspect -200 nodata')
                meta['class_legend']={str(v):name for v,name in {
                    10:'water',11:'very_low_rural',12:'low_rural',13:'rural_cluster',
                    21:'peri_urban',22:'semi_dense',23:'dense_cluster',30:'urban_centre'}.items()}
            elif kind=='pixel_m2':
                if sample['min'] is not None and sample['min']<0:raise ValueError('Negative built area m2')
                if sample['max'] is not None and sample['max']>1_000_005:
                    raise ValueError('Original 1km pixel built m² >1,000,000: wrong band/units')
            elif kind=='pixel_count':
                if sample['min'] is not None and sample['min']<0:
                    raise ValueError('Population pixel count negative')
            # Reject wrong years/families in official name or ZIP audit proof.
            proof=p.with_name(p.name+'.source.json')
            if proof.is_file():
                from .core import read_json
                j=read_json(proof)
                source_name=(str(j.get('member',''))+' '+str(j.get('archive',{}).get('path',''))).upper()
                expected_year=contract['epoch']
                if 'E'+expected_year not in source_name:
                    raise ValueError('Source ZIP/GeoTIFF source year not matching profile '+profile)
                if profile=='ghsl_smod_2020' and not ('V2_0' in source_name or 'V2-0' in source_name):
                    raise ValueError('Only SMOD V2-0 approved; archived source is different version')
                if kind=='pixel_m2' and ('GHS_BUILT_S' not in source_name or
                   (profile=='ghsl_nres_2020')!=('NRES' in source_name)):
                    raise ValueError('GHSL source family mismatched to indicator')
                if kind=='pixel_count' and 'GHS_POP' not in source_name:
                    raise ValueError('Population raster product name does not match GHS-POP')
                meta['zip_member_crc_verified']=j.get('status')=='VERIFIED_AGAINST_ZIP_CRC32'
            else:
                warnings.append('Raw TIFF lacks source ZIP sidecar; downloaded version/year requires independent check')
            meta['native_unit_contract']='GHSL_PIXELS_IN_SOURCE_GRID_VERIFIED_METADATA'
        elif profile.startswith('worldclim_'):
            if not ds.crs.is_geographic or not all(abs(v-1/120)<.0001 for v in ds.res):
                raise ValueError('Expected official 30 arcsecond WorldClim geographic grid')
            warnings.append('WorldClim historical reference 1970-2000; verify source scale/offset and units')
        elif profile.startswith('gmted_'):
            if not ds.crs.is_geographic or not all(abs(v-1/120)<.0001 for v in ds.res):
                raise ValueError('Expected actual GMTED derived 30 arcsecond source')
            warnings.append('GMTED mean/maximum descriptions and units not independently resolved')
        elif profile=='grip_density':
            if not ds.crs.is_geographic or not all(abs(v-1/12)<.0001 for v in ds.res):
                raise ValueError('Expected GRIP4 5 arcminute geographical density grid')
        elif profile.startswith('gisd'):
            if not ds.crs.is_projected or not all(abs(v-1000)<.001 for v in ds.res):
                raise ValueError('GISD profile expects precomputed 1km EPSG6933 fraction raster')
            if sample['min'] is not None and not (-.0001<=sample['min']<=sample['max']<=1.0001):
                raise ValueError('GISD projected 1km impervious fraction must be within 0–1')
        else:raise ValueError('Missing physical source contract implementation: '+profile)
        meta['warnings']=warnings
        meta['status']='METADATA_CONTRACT_PASS_BUT_UNITS_EXTERNAL_QA_REQUIRED' if warnings else 'METADATA_CONTRACT_PASS'
    out=Path(out)
    if out.exists():
        from .core import read_json
        prior=read_json(out)
        if prior.get('source')==meta['source'] and prior.get('profile')==profile:
            return {'status':'REUSED_EXISTING_SOURCE_QA','path':str(out)}
        raise FileExistsError('Different dataset/metadata; choose new QA version path')
    json_write(out,meta)
    return {'status':meta['status'],'path':str(out),'sample':sample,
            'warnings':warnings,'crs':meta['crs'],'resolution':meta['resolution']}
