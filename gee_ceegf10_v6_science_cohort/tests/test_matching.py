import pandas as pd, numpy as np, pytest
from cee_v6.cohort import generate_calendar_candidates
from cee_v6.matching import attach_weather,weather_match

def _data():
    c=pd.DataFrame([{'case_id':'C1','grid_id':'5_7','date_utc':'2022-06-01',
                     'city_id':'cityA','case_control':'reported_case'}])
    f,_=generate_calendar_candidates(c,n_candidates=3)
    dates=f[['grid_id','date_utc']].drop_duplicates().copy()
    dates['imerg_n_obs_day']=48; dates['imerg_n_obs_pre7d']=336;dates['imerg_n_obs_pre30d']=1440
    dates['imerg_day_mm']=[51.,49.,48.,50.]
    dates['imerg_rolling3h_max_mm']=[25.,24.,23.,25.]
    dates['imerg_pre7d_mm']=[90.]*4;dates['imerg_pre30d_mm']=[180.]*4
    dates['era5_soil_l1_prevday_m3m3']=[.25]*4
    dates['era5_t2m_prevday_C']=[20.]*4
    dates['era5_rain_prevday_mm']=[0.]*4
    return f,dates

def policy():
    return {'minimum_case_24h_mm':20.,'minimum_control_24h_mm':20.,
      'max_relative_24h_difference':.3,'max_relative_3h_difference':.3,
      'n_controls':2,'reference_threshold_source':'pre-registered sensitivity 20mm; climate percentile pending'}

def test_weather_matched_controls_are_unlabeled_not_negative():
    f,w=_data();x=attach_weather(f,w);result,q=weather_match(x,policy())
    assert q['status']=='WEATHER_MATCHED_STORM_PENDING'
    assert not q['independent_inundation_negative_label']
    assert q['n_cases']==1 and q['n_matched_unreported_exposures']==2
    assert set(result.case_control)=={'reported_case','matched_unreported_exposure'}
    with pytest.raises(ValueError,match='Independent storm'):
        weather_match(x,policy(),require_independent_storm=True)

def test_missing_half_hour_count_invalidates_comparison():
    f,w=_data();w.loc[1,'imerg_n_obs_day']=47
    x=attach_weather(f,w)
    assert (~x.meteo_complete).sum()==1
    y,q=weather_match(x,policy());assert q['n_matched_unreported_exposures']==2

def test_era_missing_not_zero_filled():
    f,w=_data();w.loc[0,'era5_soil_l1_prevday_m3m3']=np.nan
    x=attach_weather(f,w)
    with pytest.raises(ValueError,match='No weather-matched'):
        weather_match(x,policy())

def test_publication_mode_requires_local_climatology():
    f,w=_data();x=attach_weather(f,w)
    with pytest.raises(ValueError,match='local daily P95'):
        weather_match(x,policy(),publication=True)
    p95=pd.DataFrame({'grid_id':['5_7'],'p95_daily_mm':[60.],
      'baseline_start_year':[2001],'baseline_end_year':[2020],
      'climatology_source':['independently precomputed ERA5-Land daily percentile']})
    with pytest.raises(ValueError,match='No weather-matched'):
        weather_match(x,policy(),publication=True,climate_thresholds=p95)
