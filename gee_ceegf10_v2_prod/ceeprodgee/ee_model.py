"""Bounded v2 static and date-scoped dynamic EE expressions.

Requires an active ee.Initialize(project=...). Functions do not submit tasks.
Every static evaluation is restricted to a 10x10 (MERIT) or 5x5 (WC) tile.
WARNING: Offline source-graph tests cannot replace online Gate C equivalence.
"""
from __future__ import annotations
from .contract import MERIT_BANDS,WC_BANDS,WC_CODES

TRANSFORM_10=[10000,0,0,0,-10000,0]
TRANSFORM_100=[100,0,0,0,-100,0]

def _mean_to_10(ee,source,region,wkt,first=500):
    p=[first,0,0,0,-first,0]
    return (ee.Image(source).clip(region)
        .reduceResolution(reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=4096)
        .reproject(crs=wkt,crsTransform=p)
        .reduceResolution(reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=16384)
        .reproject(crs=wkt,crsTransform=TRANSFORM_10))

def _max_to_10(ee,source,region,wkt):
    return (ee.Image(source).clip(region)
        .reduceResolution(reducer=ee.Reducer.max(),bestEffort=False,maxPixels=4096)
        .reproject(crs=wkt,crsTransform=[500,0,0,0,-500,0])
        .reduceResolution(reducer=ee.Reducer.max(),bestEffort=False,maxPixels=16384)
        .reproject(crs=wkt,crsTransform=TRANSFORM_10))

def _percentiles_to_10(ee,source,region,wkt,percentiles,labels):
    # Direct source-pixel percentile, NOT percentile of 500m percentiles.
    return (ee.Image(source).clip(region)
        .reduceResolution(reducer=ee.Reducer.percentile(percentiles),
                          bestEffort=False,maxPixels=65536)
        .reproject(crs=wkt,crsTransform=TRANSFORM_10).rename(list(labels)))

def merit(ee,region,wkt):
    src=ee.Image('MERIT/Hydro/v1_0_1')
    hand=src.select('hnd');up=src.select('upa');water=src.select('wat')
    slope=ee.Terrain.slope(src.select('elv'))
    stats=ee.Image.cat([
        hand.rename(MERIT_BANDS[0]),
        src.select('elv').rename(MERIT_BANDS[1]),
        up.rename(MERIT_BANDS[2]),
        water.eq(1).rename(MERIT_BANDS[3]),
        hand.mask().unmask(0).rename(MERIT_BANDS[4]),
        hand.lte(2).rename(MERIT_BANDS[5]),
        hand.lte(5).rename(MERIT_BANDS[6]),
        hand.lte(10).rename(MERIT_BANDS[7]),
        slope.rename(MERIT_BANDS[8]),
        slope.lte(2).rename(MERIT_BANDS[9])])
    a=_mean_to_10(ee,stats,region,wkt)
    b=_max_to_10(ee,up,region,wkt).rename(MERIT_BANDS[10])
    lg=b.max(0).add(1).log().rename(MERIT_BANDS[11])
    ps=_percentiles_to_10(ee,hand,region,wkt,[10,50,90],MERIT_BANDS[12:15])
    up90=_percentiles_to_10(ee,up,region,wkt,[90],MERIT_BANDS[15:16])
    out=ee.Image.cat([a,b,lg,ps,up90]).toFloat()
    return out.rename(list(MERIT_BANDS)).clip(region)

def worldcover(ee,region,land_geometry,wkt):
    """25 fields. Derive class-by-land intersection BEFORE dividing by land area."""
    # The mosaic needs an explicit nominal projection; native 10m classes
    # must not become a default 1deg classification raster.
    wc=(ee.ImageCollection('ESA/WorldCover/v200').mosaic().select('Map')
        .setDefaultProjection(ee.Projection('EPSG:4326').atScale(10)))
    land=ee.Image.constant(1).clip(land_geometry).unmask(0).rename('land')
    valid=wc.mask().unmask(0).rename('valid')
    full=[wc.eq(k).unmask(0).rename(f'full_{k}') for k in WC_CODES]
    inter=[wc.eq(k).unmask(0).multiply(land).rename(f'land_{k}') for k in WC_CODES]
    # All components share a zero-filled full-cell reference and equal-area
    # two-pass 10m->100m->10km mean. No nearest-neighbor downsampling.
    components=full+[valid]+inter+[valid.multiply(land).rename('valid_land'),land]
    original=ee.Image.cat(components).toFloat().clip(region)
    coarse=(original.reduceResolution(reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=256)
        .reproject(crs=wkt,crsTransform=TRANSFORM_100))
    a=(coarse.reduceResolution(reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=16384)
        .reproject(crs=wkt,crsTransform=TRANSFORM_10))
    den=a.select('land')
    # Update mask instead of silently turning divide-by-zero coastal cells into zero.
    safe_den=den.updateMask(den.gt(0))
    final=ee.Image.cat(
        [a.select(f'full_{k}').rename(f'wc_{k}_fraction_fullcell') for k in WC_CODES]
        +[a.select('valid').rename('wc_valid_fraction_fullcell')]
        +[a.select(f'land_{k}').divide(safe_den).rename(f'wc_{k}_fraction_land') for k in WC_CODES]
        +[a.select('valid_land').divide(safe_den).rename('wc_valid_fraction_land'),
          den.rename('wc_gshhg_land_fraction_raster')])
    return final.toFloat().rename(list(WC_BANDS)).clip(region)

def event_image(ee,date_utc):
    """Do not use event-day daily ERA5 covariates as antecedents."""
    date=ee.Date(date_utc)
    # IMERG V07 `status=permanent` avoids mixing preliminary and final estimates.
    # If D is beyond availability, observation-count QC will block release.
    c=ee.ImageCollection('NASA/GPM_L3/IMERG_V07').filter(ee.Filter.eq('status','permanent')).select('precipitation')
    def halfhour(img):return (ee.Image(img).multiply(0.5).rename('depth_mm')
                              .copyProperties(img,['system:time_start']))
    rain=c.filterDate(date.advance(-30,'day'),date.advance(1,'day')).map(halfhour)
    day=rain.filterDate(date,date.advance(1,'day'))
    # 48 windows each summing 6 half-hour depth values, with midnight-day
    # overlap resolved using the preceding day. Store completeness separately.
    def complete_threehour(idx):
        group=rain.filterDate(
          date.advance(ee.Number(idx).subtract(5).multiply(30),'minute'),
          date.advance(ee.Number(idx).add(1).multiply(30),'minute'))
        # Missing halfhours must not appear as valid low rainfall.
        return group.sum().updateMask(group.count().eq(6))
    wins=ee.List.sequence(0,47).map(complete_threehour)
    max3=ee.ImageCollection.fromImages(wins).max().rename('imerg_rolling3h_max_mm')
    prev=ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').filterDate(
         date.advance(-1,'day'),date).first()
    return ee.Image.cat([
        day.sum().rename('imerg_day_mm'),
        day.max().multiply(2).rename('imerg_peak_30min_mm_h'),
        max3,
        rain.filterDate(date.advance(-7,'day'),date).sum().rename('imerg_pre7d_mm'),
        rain.filterDate(date.advance(-14,'day'),date).sum().rename('imerg_pre14d_mm'),
        rain.filterDate(date.advance(-30,'day'),date).sum().rename('imerg_pre30d_mm'),
        day.count().rename('imerg_n_obs_day'),
        rain.filterDate(date.advance(-7,'day'),date).count().rename('imerg_n_obs_pre7d'),
        rain.filterDate(date.advance(-14,'day'),date).count().rename('imerg_n_obs_pre14d'),
        rain.filterDate(date.advance(-30,'day'),date).count().rename('imerg_n_obs_pre30d'),
        prev.select('volumetric_soil_water_layer_1').rename('era5_soil_l1_prevday_m3m3'),
        prev.select('volumetric_soil_water_layer_2').rename('era5_soil_l2_prevday_m3m3'),
        prev.select('temperature_2m').subtract(273.15).rename('era5_t2m_prevday_C'),
        prev.select('total_precipitation_sum').multiply(1000).rename('era5_rain_prevday_mm'),
        prev.select('surface_runoff_sum').multiply(1000).rename('era5_runoff_prevday_mm'),
        prev.select('u_component_of_wind_10m').rename('era5_u_prevday_ms'),
        prev.select('v_component_of_wind_10m').rename('era5_v_prevday_ms'),
        prev.select('u_component_of_wind_10m').pow(2).add(
            prev.select('v_component_of_wind_10m').pow(2)).sqrt().rename('era5_wind_prevday_ms'),
    ]).toFloat()
