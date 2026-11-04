"""True 10km spatial-then-temporal IMERG rolling rainfall and D-1 ERA5-Land.

Remains source-resolution-limited (~0.1 degree), not 10m localized rainfall.
Only a bounded, single-date 10km GF10 rectangle per batch task. GEE
submission is opt-in and disabled by default in cli.
"""
from __future__ import annotations
import datetime as dt
from .base import atomic_json,load_json,utc_now

PERMANENT_END='2025-09-30' # last inclusive UTC date for IMERG V07 final status
WIN3_CADENCE_MIN=30
WIN3_N=6
OBS_COUNTS={'day':48,'pre7d':336,'pre30d':1440}
METEO_BANDS=(
 'imerg_day_mm','imerg_rolling3h_max_mm','imerg_pre7d_mm','imerg_pre30d_mm',
 'imerg_obs_day','imerg_obs_pre7d','imerg_obs_pre30d',
 'era5_soil_l1_prevday_m3m3','era5_soil_l2_prevday_m3m3',
 'era5_t2m_prevday_C','era5_rain_prevday_mm','era5_negative_rain_source_flag')
TRANSFORM=[10000,0,0,0,-10000,0]

def validated_date(value,development_start='2021-01-01',last_permanent=PERMANENT_END):
    if not isinstance(value,str):raise ValueError('UTC date required as ISO YYYY-MM-DD string')
    d=dt.date.fromisoformat(value)
    if d.isoformat()!=value:raise ValueError('Canonical YYYY-MM-DD UTC day required')
    if not development_start<=value<=last_permanent:
        raise ValueError(f'{value}: only frozen 2021-01-01..{last_permanent} IMERG V07 permanent dates accepted')
    return d

def _mean_area_10(ee,im,region,wkt,native_projection=None):
    # For native 0.1 degree imagery, max 64 source pixels per 10km output is ample.
    # Pixel-overlap weighting is handled by reduceResolution; no nearest sampling.
    source=ee.Image(im)
    if native_projection is not None: source=source.setDefaultProjection(native_projection)
    return (source.clip(region)
            .reduceResolution(ee.Reducer.mean(),maxPixels=64,bestEffort=False)
            .reproject(crs=wkt,crsTransform=TRANSFORM).clip(region))

def _sum_observed(ee,collection,start,end,expected,region,wkt,outname,native_projection):
    subset=collection.filterDate(start,end)
    count=subset.count()
    depth=subset.sum().multiply(0.5).updateMask(count.eq(expected))
    return _mean_area_10(ee,depth,region,wkt,native_projection).rename(outname), \
           _mean_area_10(ee,count,region,wkt,native_projection)

def event_image(ee,date_utc,roi,wkt):
    """Pre-register all time/space operators. No 30-day daily sum leakage.

    The rolling 3h max is max_t (mean_GF10 sum_{6 halfhours} rain_depth)
    NOT mean_GF10(max_t rain_3hour). Includes previous-day halfhours for
    rolling windows ending 00:00..23:30 UTC of event calendar day.
    """
    validated_date(date_utc)
    d=ee.Date(date_utc)
    c=(ee.ImageCollection('NASA/GPM_L3/IMERG_V07')
        .filter(ee.Filter.eq('status','permanent'))
        .select('precipitation'))
    native=ee.Image(c.filterDate(d.advance(-30,'day'),d.advance(1,'day')).first()).projection()
    day,ct_day=_sum_observed(ee,c,d,d.advance(1,'day'),48,roi,wkt,METEO_BANDS[0],native)
    pre7,ct7=_sum_observed(ee,c,d.advance(-7,'day'),d,336,roi,wkt,METEO_BANDS[2],native)
    pre30,ct30=_sum_observed(ee,c,d.advance(-30,'day'),d,1440,roi,wkt,METEO_BANDS[3],native)
    # Each 6-half-hour window (ending on current UTC day) is aggregated spatially
    # BEFORE applying the maximum temporal reducer, preserving intended logic.
    def end_slot(i):
        i=ee.Number(i)
        start=d.advance(i.subtract(5).multiply(30),'minute')
        end=d.advance(i.add(1).multiply(30),'minute')
        frames=c.filterDate(start,end)
        val=frames.sum().multiply(0.5).updateMask(frames.count().eq(6))
        return _mean_area_10(ee,val,roi,wkt,native).rename('p3h')
    rolling=(ee.ImageCollection.fromImages(ee.List.sequence(0,47).map(end_slot))
             .max().rename(METEO_BANDS[1]))
    prev=(ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
          .filterDate(d.advance(-1,'day'),d).first())
    prev=ee.Image(prev)
    era=prev.select(['volumetric_soil_water_layer_1','volumetric_soil_water_layer_2',
       'temperature_2m','total_precipitation_sum'])
    era_bands=ee.Image.cat([
      era.select('volumetric_soil_water_layer_1').rename(METEO_BANDS[7]),
      era.select('volumetric_soil_water_layer_2').rename(METEO_BANDS[8]),
      era.select('temperature_2m').subtract(273.15).rename(METEO_BANDS[9]),
      # Known negative source flow totals must be flagged, not silently accepted.
      era.select('total_precipitation_sum').multiply(1000).updateMask(
        era.select('total_precipitation_sum').gte(0)).rename(METEO_BANDS[10]),
      era.select('total_precipitation_sum').lt(0).rename(METEO_BANDS[11]),
    ])
    era10=_mean_area_10(ee,era_bands,roi,wkt,prev.select('temperature_2m').projection())
    out=ee.Image.cat([day,rolling,pre7,pre30,
                      ct_day.rename(METEO_BANDS[4]),
                      ct7.rename(METEO_BANDS[5]),
                      ct30.rename(METEO_BANDS[6]),era10])
    return out.toFloat().rename(list(METEO_BANDS))

def make_event_plan(events,grid,block=50):
    import pandas as pd
    if block not in (10,20,50,100):raise ValueError('Event large-area block only in 10/20/50/100 GF10')
    if not {'grid_id','date_utc'}.issubset(events.columns):
        raise ValueError('Case-control dates require grid_id, date_utc columns')
    sample=events[['grid_id','date_utc']].copy()
    sample.grid_id=sample.grid_id.astype(str)
    for d in sample.date_utc.dropna().astype(str).unique():validated_date(d)
    if sample.date_utc.isna().any():raise ValueError('Missing case/control event UTC date')
    # Distinct sources of case/control data require original 10km geometry remapping.
    sample=sample.drop_duplicates(['grid_id','date_utc'])
    joined=sample.merge(grid[['grid_id','grid_x','grid_y']],on='grid_id',validate='many_to_one')
    if len(joined)!=len(sample):raise ValueError('Unknown/legacy 20km grid_id in events')
    joined['bx']=(joined.grid_x//block)*block
    joined['by']=(joined.grid_y//block)*block
    schedule=(joined.groupby(['date_utc','bx','by'],sort=True)
              .agg(n_grid_days=('grid_id','size')).reset_index())
    schedule['tile_size']=block
    schedule['key']=[f'met_{d}_{x}_{y}_{block}' for d,x,y in zip(schedule.date_utc,schedule.bx,schedule.by)]
    return joined,schedule

def validate_weather_raster(path,x,y,dimension,expected_bands=METEO_BANDS):
    import numpy as np
    import rasterio
    from rasterio.transform import Affine
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_epsg()!=6933:raise ValueError('Raster not EPSG6933')
        if src.count!=len(expected_bands) or (src.width,src.height)!=(dimension,dimension):
            raise ValueError('Wrong GF10 tile size/band count')
        should=Affine(10000,0,x*10000,0,-10000,(y+dimension)*10000)
        if not src.transform.almost_equals(should):raise ValueError('Raster GF10 10km lattice mismatch')
        if src.nodata is None:raise ValueError('NoData required; missing is not zero')
        values=src.read(masked=True).filled(float('nan'))
    if np.isfinite(values[0]).any():
        rain=values[:4]
        if np.nanmin(rain)<-1e-5:raise ValueError('Negative physical IMERG rainfall')
        # max rolling three hour can exceed same calendar-day total due to previous-day overlap.
        if np.nanmax(values[4])>48.01 or np.nanmax(values[5])>336.01 or np.nanmax(values[6])>1440.01:
            raise ValueError('IMERG expected half-hour observation counts exceeded')
    return {'pixel_count':dimension*dimension,'n_bands':len(expected_bands),
            'valid_imerg_day_cells':int(np.isfinite(values[0]).sum()),
            'valid_era5_prevday_cells':int(np.isfinite(values[7]).sum()),
            'crs':'EPSG:6933','spatial_operator':'native 0.1 degree overlap-weighted area mean GF10, then temporal max3h'}
