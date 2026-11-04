import datetime as dt
import numpy as np
import pandas as pd
import pytest
from ceeopt.cost import budget,projected_hours,WC_EECU_400
from ceeopt.weather import validated_date,make_event_plan,OBS_COUNTS,METEO_BANDS,validate_weather_raster


def test_global_worldcover_eecu_would_exceed_contributor_budget():
    b=budget()
    assert b['worldcover_global_LINEAR_SCENARIO_h']>6500
    assert b['merit_global_LINEAR_SCENARIO_h']<700
    assert b['worldcover_if_downloaded_official_2021_map_local_GEE_EECU_h']==0
    assert b['global_worldcover_gee_authorized'] is False


def test_weather_utc_permanent_cutoff():
    assert validated_date('2025-09-30')==dt.date(2025,9,30)
    for s in ('2025-10-01','2026-01-01','2020-12-31','2023-3-1'):
        with pytest.raises(ValueError):validated_date(s)
    assert OBS_COUNTS=={'day':48,'pre7d':336,'pre30d':1440}
    assert len(METEO_BANDS)==12


def test_weather_plan_dedupe_and_negative_tiles_and_prevent_legacy_ids():
    g=pd.DataFrame({'grid_id':['-1_0','0_0','100_100'],'grid_x':[-1,0,100],
                    'grid_y':[0,0,100]})
    events=pd.DataFrame({'grid_id':['-1_0','-1_0','0_0'],
                         'date_utc':['2023-06-01','2023-06-01','2023-06-01']})
    rows,plan=make_event_plan(events,g,50)
    assert len(rows)==2 and len(plan)==2
    assert set(plan.bx)=={-50,0}
    with pytest.raises(ValueError,match='Unknown/legacy'):
        make_event_plan(pd.DataFrame({'grid_id':['missing'],'date_utc':['2023-06-01']}),g,50)


def test_weather_raster_10km_12band_audit(tmp_path):
    import rasterio
    from rasterio.transform import Affine
    p=tmp_path/'met_100_200_2.tif'
    a=np.ones((12,2,2),dtype=np.float32)
    a[4]=48;a[5]=336;a[6]=1440
    with rasterio.open(p,'w',driver='GTiff',width=2,height=2,count=12,dtype='float32',
            crs='EPSG:6933',transform=Affine(10000,0,1000000,0,-10000,2020000),nodata=-9999) as ds:
        ds.write(a)
    qc=validate_weather_raster(p,100,200,2)
    assert qc['valid_imerg_day_cells']==4
    with rasterio.open(p,'r+') as ds:
        pass
    with pytest.raises(ValueError,match='mismatch'):
        validate_weather_raster(p,101,200,2)
