"""Join independently built storm exposure universe with incomplete news labels.

Unreported grid-storm days are UNLABELED (not confirmed non-flood).
Never create the exposure universe by sampling only news observations.
"""
import re
import pandas as pd
from .paths import safe_output,atomic_json

WEATHER=['grid_id','date','storm_id','city_id','rain_24h_mm','rain_3h_mm','api_7d_mm']
STATIC=['grid_id','hand_m','slope_deg','urban_fraction_2020','vegetation_fraction']

def assemble(root,weather,static,labels,tag=None):
    if tag is not None and not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Panel tag must be a single fig2_* version name")
    w=pd.read_parquet(weather);s=pd.read_parquet(static);l=pd.read_parquet(labels)
    for name,required,frame in [('weather',WEATHER,w),('static',STATIC,s),
                                ('labels',['event_id','grid_id','date','geocode_quality'],l)]:
        missing=set(required)-set(frame.columns)
        if missing:raise ValueError(f'{name} missing {sorted(missing)}')
    for x in (w,l):x['date']=pd.to_datetime(x.date,errors='raise').dt.normalize()
    # 2020 fixed SMOD and 2021 WorldCover are retrospective context only.
    # Never use them to claim prospective prediction of earlier events.
    if (w.date < pd.Timestamp('2021-01-01')).any():
        raise ValueError('Pre-2021 exposures require historically matched land-cover and urban predictors')
    for x in (w,s,l):x['grid_id']=x.grid_id.astype(str)
    if w.duplicated(['grid_id','date']).any():
        raise ValueError('Multiple storm IDs per grid-day: resolve attribution before assigning news labels')
    if s.duplicated('grid_id').any():raise ValueError('Duplicate static grid IDs')
    if w[WEATHER].isna().any().any():raise ValueError('Missing storm/weather data; never fill zero')
    for col in ('rain_24h_mm','rain_3h_mm','api_7d_mm'):
        w[col]=pd.to_numeric(w[col],errors='raise')
        if (w[col]<0).any():raise ValueError('Negative rainfall: '+col)
    high=l.loc[l.geocode_quality.eq('HIGH_GEOCODE_SPECIFICITY'),
               ['event_id','grid_id','date']].drop_duplicates()
    counts=high.groupby(['grid_id','date']).event_id.nunique().rename('n_report_uuids')
    w=w.join(counts,on=['grid_id','date'])
    w['n_report_uuids']=w.n_report_uuids.fillna(0).astype('int32')
    w['observed_news_onset']=(w.n_report_uuids>0).astype('int8')
    w['target_semantics']='positive_vs_unlabeled_not_true_flood_vs_no_flood'
    w=w.merge(s,on='grid_id',how='left',validate='many_to_one',suffixes=('','_static'))
    for col in STATIC[1:]:
        if w[col].isna().any():raise ValueError('Missing static feature '+col)
    if not w.observed_news_onset.any():raise ValueError('No positive labels in complete weather exposure frame')
    base="outputs/panels/" if tag is None else "outputs/panels/"+tag+"/"
    output=safe_output(root,base+"storm_exposure_with_news_labels.parquet")
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError(output)
    w.to_parquet(output,index=False)
    observed_keys=w.set_index(['grid_id','date']).index
    qc={'status':'PASS_WEATHER_LABEL_MERGE','total_grid_storm_days':len(w),
        'news_positive_exposures':int(w.observed_news_onset.sum()),
        'unlabeled_exposures':int((w.observed_news_onset==0).sum()),
        'unmatched_high_specificity_report_grid_days':int(
            len(counts.index.difference(observed_keys))),
        'warning':'Unlabeled is NOT flood-free; labels are not true flood probabilities'}
    path="reports/qc/panel_qc.json" if tag is None else "reports/qc/"+tag+"/panel_qc.json"
    atomic_json(safe_output(root,path),qc)
    return qc
