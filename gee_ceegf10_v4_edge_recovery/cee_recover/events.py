"""Strict case/control GF10 x UTC date design gate; no invented negatives.

This module only validates an *already curated* event/control study cohort.
A Groundsource reporting day is NOT sufficient to call a row a non-flood control.
"""
from __future__ import annotations
import argparse,pathlib,json
from . import io

REQUIRED={'grid_id','date_utc','case_control','pair_id','storm_id','city_id','label_source','sampling_protocol'}
ALLOWED={'reported_case','matched_unreported_exposure'}

def validate(events,grid,allow_missing_storm=False):
    import pandas as pd
    missing=REQUIRED-set(events.columns)
    if missing:raise ValueError('Study cohort is not independently frozen. Missing columns: '+str(sorted(missing)))
    d=events.copy()
    if len(d)==0:raise ValueError('Empty cohort')
    if d[list(REQUIRED)].isna().any().any():raise ValueError('Missing required audited sampling metadata')
    if not set(d.case_control).issubset(ALLOWED):
        raise ValueError('Do not label absence of news as a verified non-flood negative')
    if d[['grid_id','date_utc','case_control']].duplicated().any():
        raise ValueError('Duplicate grid-day-case category; collapse event records upstream with audit trail')
    if d[['grid_id','date_utc']].duplicated().any():
        raise ValueError('Same grid/date cannot be both a case and its control')
    if not (d.grid_id.astype(str).str.fullmatch(r'-?\d+_-?\d+')).all():
        raise ValueError('grid_id not frozen GF10 x_y')
    ids=set(grid.grid_id.astype(str))
    if not set(d.grid_id.astype(str)).issubset(ids):
        raise ValueError('Old GF10 or unmapped Groundsource dates detected')
    dates=pd.to_datetime(d.date_utc,utc=True,errors='raise',format='mixed')
    if not dates.dt.hour.eq(0).all() or not dates.dt.minute.eq(0).all() or not dates.dt.second.eq(0).all():
        raise ValueError('Dates must be full UTC days at midnight, not event timestamps')
    if (dates.dt.year.lt(2021)|dates.dt.year.gt(2025)).any():
        raise ValueError('Frozen figure 2 event window is 2021-2025 and must respect permanent IMERG availability')
    if not (d.label_source.astype(str).str.len().gt(3)).all():
        raise ValueError('Provenance needs meaningful label source, not a placeholder')
    if not (d.sampling_protocol.astype(str).str.len().gt(10)).all():
        raise ValueError('Control sampling provenance missing')
    g=d.groupby('pair_id',sort=False).case_control.agg(lambda x:set(x))
    if not all(v==ALLOWED for v in g):
        raise ValueError('Every pair_id must include at least one case and one matched unreported exposure control')
    if d.storm_id.astype(str).str.lower().isin(['unknown','none','nan','']).any() and not allow_missing_storm:
        raise ValueError('storm_id missing: freeze event storm linkage or explicitly acknowledge no independent storm split')
    # Each pair is only within one city's independently sampled risk set.
    if d.groupby('pair_id').city_id.nunique().max()>1:
        raise ValueError('Control pair spans multiple cities: revise the matching contract')
    return d.assign(date_utc=dates.dt.strftime('%Y-%m-%d'))

def run(args):
    import pandas as pd
    from .run import conf,HOME
    c=conf()
    g=pd.read_parquet(c['grid_path'],columns=['grid_id','grid_x','grid_y'])
    source=pathlib.Path(args.input)
    if not source.exists():raise FileNotFoundError('No case/control cohort provided. Original Figure 1 news days are not controls.')
    data=pd.read_parquet(source) if source.suffix.lower()=='.parquet' else pd.read_csv(source)
    output=validate(data,g,args.allow_missing_storm)
    p=HOME/'plans'/'frozen_case_control_gf10_utc_v4.parquet'
    if p.exists():
        raise FileExistsError('Cohort already frozen; do not overwrite for another model experiment')
    output.to_parquet(p,index=False)
    meteorology=output[['grid_id','date_utc']].drop_duplicates().copy()
    # The cost unit is a unique meteorological grid-day, not case/control label.
    from ceeprodgee.grid import event_plan_from_records
    event_days,work=event_plan_from_records(meteorology,g)
    event_days.to_parquet(HOME/'plans'/'event_gf10_days_v4.parquet',index=False)
    work.to_csv(HOME/'plans'/'event_gee_tasks_v4.csv',index=False)
    r={'status':'AUDITED_INPUT_SCHEMA_PASS_NOT_FLOOD_TRUTH',
       'source_sha256':io.sha(source),'n_rows':len(output),
       'n_cases':int((output.case_control=='reported_case').sum()),
       'n_unreported_comparators':int((output.case_control=='matched_unreported_exposure').sum()),
       'n_unique_meteorological_grid_days':len(meteorology),'n_event_task_groups':len(work),
       'storm_grouping_available':not args.allow_missing_storm,
       'warning':'These controls are unlabeled/unreported exposure, NOT independently verified non-flood days.'}
    io.atomic(HOME/'reports'/'event_cohort_input_qc.json',r)
    print(json.dumps(r,indent=2));return r

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--allow-missing-storm',action='store_true')
    run(p.parse_args())
if __name__=='__main__':main()
