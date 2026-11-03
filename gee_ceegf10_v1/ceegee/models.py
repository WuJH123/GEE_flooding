"""Frozen source and physical units. No GEE assets are altered by these functions."""
from __future__ import annotations

WORLD_CODES = (10,20,30,40,50,60,70,80,90,95,100)
STATIC_FAMILIES = ('merit','worldcover')


def _aggregate(ee, img, max_pixels=16384):
    return img.reduceResolution(reducer=ee.Reducer.mean(), bestEffort=False, maxPixels=max_pixels)


def merit_native(ee):
    source=ee.Image('MERIT/Hydro/v1_0_1')
    return ee.Image.cat([
      source.select('hnd').rename('merit_hand_mean_m'),
      source.select('elv').rename('merit_elv_mean_m'),
      source.select('upa').rename('merit_upa_mean_km2'),
      source.select('wat').eq(1).rename('merit_permanent_water_fraction'),
      source.select('hnd').mask().unmask(0).rename('merit_valid_fraction'),
    ]).toFloat()


def merit_10km(ee):
    src=merit_native(ee)
    # Equal-area two-stage aggregation prevents huge 3 arc-second pixel counts
    # toward high latitudes. Explicit no-bestEffort avoids undocumented pyramid.
    means=src.reduceResolution(reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=4096).reproject(
        crs='EPSG:6933',crsTransform=[500,0,0,0,-500,0]).reduceResolution(
        reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=1024)
    peak=ee.Image('MERIT/Hydro/v1_0_1').select('upa').reduceResolution(
        reducer=ee.Reducer.max(),bestEffort=False,maxPixels=4096).reproject(
        crs='EPSG:6933',crsTransform=[500,0,0,0,-500,0]).reduceResolution(
        reducer=ee.Reducer.max(),bestEffort=False,maxPixels=1024).rename('merit_upa_max_km2')
    return means.addBands(peak).toFloat()


def worldcover_native(ee):
    wc=(ee.ImageCollection('ESA/WorldCover/v200').mosaic().select('Map')
        .setDefaultProjection(ee.Projection('EPSG:4326').atScale(10)))
    # UNMASK so fractions are per FULL 10km cell; retain valid_fraction to distinguish
    # sea/missing coverage from genuine zero. Publication land fractions need clipping.
    return ee.Image.cat(
      [wc.eq(v).unmask(0).rename(f'wc_{v}_fraction_fullcell') for v in WORLD_CODES] +
      [wc.mask().unmask(0).rename('wc_valid_fraction_fullcell')]
    ).toFloat()


def worldcover_10km(ee):
    first=worldcover_native(ee).reduceResolution(
       reducer=ee.Reducer.mean(),bestEffort=False,maxPixels=256).reproject(
       crs='EPSG:6933',crsTransform=[100,0,0,0,-100,0])
    # Mandatory 2nd stage: a one-step 10m -> 10km is 1 million native pixels / cell.
    return first.reduceResolution(reducer=ee.Reducer.mean(),
                                  bestEffort=False,maxPixels=16384).toFloat()


def static_image(ee,family):
    return {'merit':merit_10km,'worldcover':worldcover_10km}[family](ee)


def static_native(ee,family):
    return {'merit':merit_native,'worldcover':worldcover_native}[family](ee)


def climate_for_event_date(ee,date_iso):
    """Event D has day rainfall; antecedents exclude D, all timestamps in UTC."""
    d=ee.Date(date_iso)
    imerg=ee.ImageCollection('NASA/GPM_L3/IMERG_V07').select('precipitation')
    # IMERG band is intensity mm/hour and each observation covers 0.5h.
    def depth(image):
        return ee.Image(image).multiply(0.5).rename('mm_halfhour').copyProperties(image,['system:time_start'])
    rain=imerg.filterDate(d.advance(-30,'day'),d.advance(1,'day')).map(depth)
    pre7=rain.filterDate(d.advance(-7,'day'),d).sum().rename('imerg_pre7d_mm')
    pre30=rain.filterDate(d.advance(-30,'day'),d).sum().rename('imerg_pre30d_mm')
    daily=rain.filterDate(d,d.advance(1,'day')).sum().rename('imerg_event_utc_day_mm')
    # 48 sliding windows ending from 00:30 through 24:00 UTC, each 6 halfhours.
    windows=ee.List.sequence(0,47).map(lambda i:
       rain.filterDate(d.advance(ee.Number(i).subtract(5).multiply(30),'minute'),
                       d.advance(ee.Number(i).add(1).multiply(30),'minute')).sum())
    max3=ee.ImageCollection.fromImages(windows).max().rename('imerg_rolling3h_max_mm')
    imcount=imerg.filterDate(d,d.advance(1,'day')).count().rename('imerg_n_obs_day')
    imprev=imerg.filterDate(d.advance(-7,'day'),d).count().rename('imerg_n_obs_pre7d')
    imprev30=imerg.filterDate(d.advance(-30,'day'),d).count().rename('imerg_n_obs_pre30d')
    er=ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').filterDate(d.advance(-1,'day'),d)
    # Defined as previous complete UTC day, not date D nor post-event climate.
    previous=ee.Image(er.first())
    return ee.Image.cat([daily,max3,pre7,pre30,imcount,imprev,imprev30,
        previous.select('volumetric_soil_water_layer_1').rename('era5land_soilwater_l1_pre1d_m3m3'),
        previous.select('temperature_2m').subtract(273.15).rename('era5land_t2m_pre1d_C'),
        previous.select('total_precipitation_sum').multiply(1000).rename('era5land_pre1d_precip_mm')
    ]).toFloat()
