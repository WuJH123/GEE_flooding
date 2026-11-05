"""Prevent Fig1 report-day catalogs being mislabeled as independent controls.

Requires independently frozen matching cohort and source lineage.
This checks the design contract; no algorithm invents controls or flood negatives.
"""
from __future__ import annotations
import pathlib,json,hashlib

def audit(path,grid_ids,output):
    import pandas as pd
    p=pathlib.Path(path)
    if not p.is_file():raise FileNotFoundError('No audited event case-control cohort; do NOT launch event extraction from news dates')
    d=pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
    required=['grid_id','date_utc','match_set_id','case_control','source_family','sampling_rule','city_id']
    missing=set(required)-set(d.columns)
    if missing:raise ValueError('Not an independently matched case-control sample: missing '+str(sorted(missing)))
    if d[required].isna().any().any():raise ValueError('Null cohort identifiers or lineage')
    if len(d)==0 or not set(d.grid_id.astype(str)).issubset(grid_ids):raise ValueError('Unknown GF10 IDs')
    if not set(d.case_control.astype(str)).issubset({'case','unlabeled_control'}):raise ValueError('Controls cannot be labeled confirmed dry days')
    if set(d.case_control.astype(str))!={'case','unlabeled_control'}:raise ValueError('Requires both cases and matched unlabeled controls')
    date=pd.to_datetime(d.date_utc,utc=True,errors='raise')
    if not all((date.dt.hour==0)&(date.dt.minute==0)&(date.dt.second==0)) or not set(date.dt.year.unique()).issubset({2021,2022,2023,2024,2025}):raise ValueError('Dates must be UTC day and frozen 2021–2025 analysis period')
    if d.duplicated(['grid_id','date_utc','match_set_id','case_control']).any():raise ValueError('Duplicate cohort membership')
    tab=d.groupby(['match_set_id','case_control']).size().unstack(fill_value=0)
    if 'case' not in tab or 'unlabeled_control' not in tab or not tab['case'].ge(1).all() or not tab['unlabeled_control'].ge(1).all():raise ValueError('Unmatched case-control sets')
    rep={'status':'COHORT_SCHEMA_QA_ONLY_NOT_CAUSAL_PROOF','n_rows':len(d),'n_match_sets':len(tab),
         'n_grid_days':len(d[['grid_id','date_utc']].drop_duplicates()),
         'source_path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
         'warning':'Unlabeled control is not verified dry; source independence and temporal leakage need separate audit'}
    pathlib.Path(output).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(output).write_text(json.dumps(rep,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    return rep
