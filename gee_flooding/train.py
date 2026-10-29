"""Interpretable M0-M2 baseline with strict joint city + independent storm holdout.

Evaluation is NEWS-REPORTED versus UNLABELED, not true flooding risk.
"""
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
from sklearn.model_selection import GroupShuffleSplit
from .paths import safe_output,atomic_json

EXPERIMENTS={
    'M0_rain':['rain_24h_mm','rain_3h_mm','api_7d_mm'],
    'M1_rain_terrain':['rain_24h_mm','rain_3h_mm','api_7d_mm','hand_m','slope_deg'],
    'M2_rain_terrain_surface':['rain_24h_mm','rain_3h_mm','api_7d_mm',
                               'hand_m','slope_deg','urban_fraction_2020','vegetation_fraction']
}

def city_storm_partition(df,seed=42,city_test_fraction=.2,storm_test_fraction=.2):
    if len(df)<50:raise ValueError('Need >=50 storm-exposed sample rows')
    if df.city_id.nunique()<5 or df.storm_id.nunique()<5:
        raise ValueError('Require >=5 cities and >=5 independently identified meteorological storms')
    idx=np.arange(len(df))
    cg=GroupShuffleSplit(n_splits=1,test_size=city_test_fraction,random_state=seed)
    sg=GroupShuffleSplit(n_splits=1,test_size=storm_test_fraction,random_state=seed+1)
    ci,cj=next(cg.split(idx,groups=df.city_id))
    si,sj=next(sg.split(idx,groups=df.storm_id))
    train=np.intersect1d(ci,si)
    test=np.intersect1d(cj,sj)
    if len(train)<20 or len(test)<5:raise ValueError('Insufficient dual-heldout data')
    if set(df.iloc[train].city_id)&set(df.iloc[test].city_id):raise AssertionError('City leakage')
    if set(df.iloc[train].storm_id)&set(df.iloc[test].storm_id):raise AssertionError('Storm leakage')
    return train,test

def metrics(y,p):
    if len(np.unique(y))<2:raise ValueError('Heldout data contain only one class')
    return {'roc_auc_news_proxy':float(roc_auc_score(y,p)),
            'pr_auc_news_proxy':float(average_precision_score(y,p)),
            'brier_news_proxy':float(brier_score_loss(y,p)),
            'test_news_positive_prevalence':float(np.mean(y))}

def run(root,panel,seed=42):
    df=pd.read_parquet(panel)
    if 'target_semantics' not in df or not df.target_semantics.eq(
            'positive_vs_unlabeled_not_true_flood_vs_no_flood').all():
        raise ValueError('Target semantics not approved')
    required=set(sum(EXPERIMENTS.values(),[])+['city_id','storm_id','observed_news_onset'])
    if required-set(df):raise ValueError('Missing required columns: '+str(sorted(required-set(df))))
    if df[['city_id','storm_id']].isna().any().any():raise ValueError('Null city/storm group')
    y=df.observed_news_onset.to_numpy(dtype=int)
    if not set(np.unique(y))<=set([0,1]):raise ValueError('Invalid label')
    i,j=city_storm_partition(df,seed)
    if len(np.unique(y[i]))<2 or len(np.unique(y[j]))<2:
        raise ValueError('One class in training or heldout data')
    results=[];final=None
    for name,cols in EXPERIMENTS.items():
        X=df.loc[:,cols].apply(pd.to_numeric,errors='coerce').to_numpy(dtype=float)
        if np.isinf(X).any():raise ValueError('Infinity in predictors')
        model=make_pipeline(SimpleImputer(strategy='median'),
                HistGradientBoostingClassifier(max_iter=180,max_leaf_nodes=15,
                                               l2_regularization=1.0,random_state=seed))
        model.fit(X[i],y[i]);p=model.predict_proba(X[j])[:,1]
        results.append({'model':name,'n_features':len(cols),**metrics(y[j],p)})
        if name=='M2_rain_terrain_surface':final=(model,cols)
    out=safe_output(root,'outputs/models');out.mkdir(parents=True,exist_ok=True)
    if (out/'M2_news_proxy_model.joblib').exists():raise FileExistsError('Model already exists')
    joblib.dump({'model':final[0],'columns':final[1],
                 'target':'news onset vs unlabeled, NOT true pluvial flood probability'},
                out/'M2_news_proxy_model.joblib')
    pd.DataFrame(results).to_csv(out/'baseline_ablation_metrics.csv',index=False)
    qc={'status':'PASS_NEWS_PROXY_BASELINE',
        'train_rows':len(i),'test_rows':len(j),
        'discarded_mixed_quadrant_rows':len(df)-len(i)-len(j),
        'train_cities':int(df.iloc[i].city_id.nunique()),
        'test_cities':int(df.iloc[j].city_id.nunique()),
        'train_storms':int(df.iloc[i].storm_id.nunique()),
        'test_storms':int(df.iloc[j].storm_id.nunique()),
        'experiments':results,
        'warning':'News-vs-unlabeled proxy metrics only; independent true flood validation is mandatory'}
    atomic_json(safe_output(root,'reports/qc/baseline_model_qc.json'),qc)
    return qc
