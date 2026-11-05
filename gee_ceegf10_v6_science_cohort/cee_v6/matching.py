"""Post-weather exposure matching; labels remain reported vs UNLABELED.

Precipitation similarity here is observational matching, NOT a causal effect
estimator and never a proof of physical no flooding on controls.
"""
from __future__ import annotations
import pandas as pd,numpy as np
from .common import readtab,writetab,save,sha
REQUIRED_RAIN=('imerg_day_mm','imerg_rolling3h_max_mm','imerg_pre7d_mm',
    'imerg_pre30d_mm','imerg_n_obs_day','imerg_n_obs_pre7d','imerg_n_obs_pre30d')


def attach_weather(candidates,weather,minimum_cases=1):
    for c in ('grid_id','date_utc')+REQUIRED_RAIN:
        if c not in weather:raise ValueError('Missing weather field '+c)
    if weather.duplicated(['grid_id','date_utc']).any():raise ValueError('Duplicate weather grid-day not permitted')
    x=candidates.merge(weather,on=['grid_id','date_utc'],how='left',validate='many_to_one',indicator=True)
    x['meteo_complete']=(x['_merge'].eq('both') & x.imerg_n_obs_day.eq(48)
         & x.imerg_n_obs_pre7d.eq(336) & x.imerg_n_obs_pre30d.eq(1440))
    # Avoid unrealistically negative ERA accumulated precipitation (known GEE source issue).
    x['era5_valid_antecedent']=(x.get('era5_soil_l1_prevday_m3m3',pd.Series(np.nan,index=x.index)).notna()
        & x.get('era5_t2m_prevday_C',pd.Series(np.nan,index=x.index)).notna()
        & x.get('era5_rain_prevday_mm',pd.Series(np.nan,index=x.index)).ge(-1e-6))
    x=x.drop(columns=['_merge'])
    if x.case_control.eq('reported_case').sum()<minimum_cases:raise ValueError('No actual reported cases in input')
    return x


def weather_match(x,policy,storm_mapping=None,require_independent_storm=False,
                  climate_thresholds=None,publication=False):
    """Only match fully measured rainy exposed dates.

    policy must be *pre-registered* and audited against climatological P95.
    A global absolute mm threshold alone is an exploratory sensitivity setting.
    """
    required={'minimum_case_24h_mm','minimum_control_24h_mm','max_relative_24h_difference',
              'max_relative_3h_difference','n_controls','reference_threshold_source'}
    if set(policy)!=required:raise ValueError('Pre-registered policy keys differ: '+str(required))
    if not policy['reference_threshold_source']:
        raise ValueError('Source/provenance of precipitation threshold required')
    if not 0<policy['n_controls']<=8:raise ValueError('n_controls must be 1..8')
    if not 0<=policy['max_relative_24h_difference']<=1 or not 0<=policy['max_relative_3h_difference']<=1:
        raise ValueError('Excessive/nonphysical caliper')
    if publication:
        if climate_thresholds is None:
            raise ValueError('Publication mode requires independently estimated GF10 local daily P95 rainfall climatology')
        required_climate={'grid_id','p95_daily_mm','baseline_start_year','baseline_end_year','climatology_source'}
        if not required_climate.issubset(climate_thresholds.columns):raise ValueError('Local climatology missing source/period/p95 fields')
        if climate_thresholds.grid_id.duplicated().any():raise ValueError('Duplicate P95 cell')
        if climate_thresholds.p95_daily_mm.isna().any() or (climate_thresholds.p95_daily_mm<0).any():
            raise ValueError('Invalid climatology threshold')
        x=x.merge(climate_thresholds[list(required_climate)],on='grid_id',how='left',validate='many_to_one')
        if x.p95_daily_mm.isna().any():raise ValueError('Case/control GF10 lacks local climatological P95; no silent fallback to 20mm')
    rows=[];excluded=[]
    for pair,group in x.groupby('pair_id',sort=True):
        case=group[group.case_control.eq('reported_case')]
        ctrl=group[group.case_control.eq('unlabeled_calendar_candidate')]
        if len(case)!=1:raise ValueError('Each pair must have exactly one reported case')
        c=case.iloc[0]
        if not c.meteo_complete or not c.era5_valid_antecedent or not pd.notna(c.imerg_day_mm) or not pd.notna(c.imerg_rolling3h_max_mm):
            excluded.append({'pair_id':pair,'reason':'CASE_METEO_INCOMPLETE'});continue
        case_threshold=max(float(policy['minimum_case_24h_mm']),float(c.p95_daily_mm)) if publication else float(policy['minimum_case_24h_mm'])
        if c.imerg_day_mm<case_threshold:
            excluded.append({'pair_id':pair,'reason':'CASE_NOT_IN_PRE_REGISTERED_RAIN_EXPOSURE'});continue
        if publication:
            ctrl=ctrl.copy()
            ctrl['control_required_mm']=ctrl.p95_daily_mm.clip(lower=float(policy['minimum_control_24h_mm']))
            rain_ok=ctrl.imerg_day_mm.ge(ctrl.control_required_mm)
        else:rain_ok=ctrl.imerg_day_mm.ge(float(policy['minimum_control_24h_mm']))
        pool=ctrl[ctrl.meteo_complete & ctrl.era5_valid_antecedent & rain_ok].copy()
        if pool.empty:
            excluded.append({'pair_id':pair,'reason':'NO_RAIN_EXPOSED_UNLABELED_COMPARATOR'});continue
        # Relative calipers use the case rainfall as scale with a 1-mm guard.
        pool['rain24_rel_diff']=(pool.imerg_day_mm-c.imerg_day_mm).abs()/max(1.,float(c.imerg_day_mm))
        pool['rain3h_rel_diff']=(pool.imerg_rolling3h_max_mm-c.imerg_rolling3h_max_mm).abs()/max(1.,float(c.imerg_rolling3h_max_mm))
        pool=pool[(pool.rain24_rel_diff<=policy['max_relative_24h_difference']) &
                  (pool.rain3h_rel_diff<=policy['max_relative_3h_difference'])].copy()
        if pool.empty:
            excluded.append({'pair_id':pair,'reason':'CALIPER_FAILURE'});continue
        pool['distance_score']=pool.rain24_rel_diff+pool.rain3h_rel_diff
        pool=pool.sort_values(['distance_score','date_utc']).head(int(policy['n_controls']))
        rec=c.to_dict();rec['rain24_rel_diff']=0.;rec['rain3h_rel_diff']=0.;rec['distance_score']=0.
        rec['case_control']='reported_case';rows.append(rec)
        for _,r in pool.iterrows():
            z=r.to_dict();z['case_control']='matched_unreported_exposure';rows.append(z)
    if not rows:raise ValueError('No weather-matched groups; do not fabricate controls')
    result=pd.DataFrame(rows)
    if storm_mapping is not None:
        columns=['grid_id','date_utc','storm_id','storm_source','storm_quality']
        if not set(columns).issubset(storm_mapping.columns):raise ValueError('Independent storm catalogue lacks required keys')
        if storm_mapping.duplicated(['grid_id','date_utc']).any():raise ValueError('Ambiguous storm assignments')
        # Never join on report timestamps alone; exact cell×UTC-day assignments.
        result=result.drop(columns=['storm_id','storm_status'],errors='ignore').merge(
            storm_mapping[columns],on=['grid_id','date_utc'],how='left',validate='many_to_one')
        result['storm_status']=np.where(result.storm_id.notna() & result.storm_source.notna() &
                                         result.storm_quality.eq('independently_verified'),
                                         'VERIFIED_INDEPENDENT','UNVERIFIED')
    else:
        result['storm_id']=pd.NA
        result['storm_status']='PENDING_INDEPENDENT_STORM_CATALOG'
    valid_storm=(result.storm_status=='VERIFIED_INDEPENDENT').all()
    if require_independent_storm and not valid_storm:
        raise ValueError('Independent storm matching unavailable: cannot claim independent-storm holdout')
    report={'status':'FINAL_MATCHED_WITH_VERIFIED_STORMS' if valid_storm else 'WEATHER_MATCHED_STORM_PENDING',
      'n_cases':int(result.case_control.eq('reported_case').sum()),
      'n_matched_unreported_exposures':int(result.case_control.eq('matched_unreported_exposure').sum()),
      'n_dropped_cases':len(excluded),'dropped_reasons':pd.DataFrame(excluded).reason.value_counts().to_dict() if excluded else {},
      'storm_verified':bool(valid_storm),'climatological_threshold_verified':bool(publication),
      'independent_inundation_negative_label':False,
      'semantics':'No news is not a physical flood-free negative; matched outcome is reported-flood response',
      'matching_policy':policy}
    return result,report
