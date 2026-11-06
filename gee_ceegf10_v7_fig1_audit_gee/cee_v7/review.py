"""Traceable UUID-to-case lineage; independent verification is an *additional* source."""
from __future__ import annotations
import datetime as dt,pathlib
import pandas as pd
from . import core

PROV='SOURCE_DERIVED_DAY_AND_UCDB_GEOMETRY_NOT_ARTICLE_VERIFIED'
REVIEW_FIELDS=['uuid','source_article_url','excerpt_confirms_flood_day','excerpt_confirms_locality',
               'reviewer1','reviewer2','reviewer1_verdict','reviewer2_verdict',
               'audit_date_utc','evidence_kind','independent_evidence_url']


def _case_membership(records):
    if records.uuid.duplicated().any():raise ValueError('Source UUID duplicated in candidate records')
    records=records.copy()
    k=['grid_id','city_id','date_utc']
    if records[k].isna().any().any():raise ValueError('Missing primary source identity')
    records['case_id']=[core.stable_id('SOURCE_CASE',x,y,d) for x,y,d in zip(records.grid_id,records.city_id,records.date_utc)]
    return records

def aggregate(records,kind='PREEXTRACTION'):
    m=_case_membership(records)
    g=m.groupby('case_id',sort=True).agg(grid_id=('grid_id','first'),city_id=('city_id','first'),
         date_utc=('date_utc','first'),source_uuid_count=('uuid','nunique'),
         min_grid_fraction=('grid_geom_fraction','min'),
         min_ucdb_fraction=('ucdb_geom_fraction','min')).reset_index()
    if g.duplicated(['grid_id','date_utc','city_id']).any():raise ValueError('Collision or duplicate grouped case')
    g['source_local_date']=g.date_utc
    g['label_source']='Groundsource_2026_news_parquet'
    g['case_control']='reported_case'
    g['pair_id']='pair_'+g.case_id
    g['storm_id']=None
    g['storm_status']='UNVERIFIED_STORM_ID'
    g['date_utc_is_source_date_proxy']=True
    g['source_date_scope']='SOURCE_SINGLE_DAY_EXTRACTED_NEEDS_UTC_PLUS_MINUS_ONE_SENSITIVITY'
    g['spatial_scope']='UCDB_GEOMETRY_OVERLAP_NOT_TRUE_FLOOD_FOOTPRINT'
    g['verified_independently']=kind=='MANUAL_VERIFIED'
    g['sampling_protocol']='UCDB_GROUND_SOURCE_SAME_GRID_EXPOSURE_V7_'+kind
    g['case_type']='REPORTED_FLOOD_NOT_INUNDATION_TRUTH'
    return g,m[['case_id','uuid','grid_id','date_utc','city_id','source_raw_row','source_geom_sha256']]

def create_cases(source,out_dir,review_n=400,seed=20261106):
    out=pathlib.Path(out_dir)
    if out.exists() and any(out.iterdir()):raise FileExistsError('Case freeze output must be a NEW directory')
    out.mkdir(parents=True,exist_ok=True)
    records=pd.read_parquet(source)
    need={'uuid','grid_id','city_id','date_utc','source_geom_sha256','source_raw_row',
          'grid_geom_fraction','ucdb_geom_fraction','date_precision_verified',
          'location_precision_verified'}
    if not need<=set(records):raise ValueError('Missing source fields '+str(need-set(records)))
    if (records.date_precision_verified.astype(bool)|records.location_precision_verified.astype(bool)).any():
        raise ValueError('Official raw Groundsource cannot be automatically marked independently verified')
    cases,membership=aggregate(records)
    cp=out/'reported_source_day_cases_PROVISIONAL.parquet';mp=out/'case_uuid_membership.parquet'
    cases.to_parquet(core.ensure_new(cp),index=False);membership.to_parquet(core.ensure_new(mp),index=False)
    # Review actual source UUIDs; stratify by year and city, then deterministic random draw.
    frame=records.copy()
    frame['year']=frame.date_utc.astype(str).str.slice(0,4)
    first=frame.groupby(['year','city_id'],sort=True).sample(n=1,random_state=seed)
    if len(first)>review_n:first=first.sample(n=review_n,random_state=seed)
    if len(first)<review_n:
        remaining=frame.loc[~frame.uuid.isin(first.uuid)]
        extra=remaining.sample(n=min(review_n-len(first),len(remaining)),random_state=seed)
        first=pd.concat([first,extra],ignore_index=True)
    for k in REVIEW_FIELDS:
        first[k]=first.uuid if k=='uuid' else ''
    first['sampling_stratum']=first['year']+'|'+first['city_id'].astype(str)
    first['precision_from_source']='EXTRACTED_NOT_VERIFIED'
    template=out/'independent_review_template.csv'
    first[REVIEW_FIELDS+['grid_id','city_id','date_utc','sampling_stratum','precision_from_source']].to_csv(core.ensure_new(template),index=False,encoding='utf-8-sig')
    report={'status':'REPORTED_SOURCE_DAY_PROVISIONAL_NOT_PUBLICATION_VERIFIED',
        'source_sha256':core.digest(source),'n_input_uuids':len(records),'n_case_grid_days':len(cases),
        'n_distinct_cities':int(cases.city_id.nunique()),'n_review_uuids_sampled':len(first),
        'article_url_in_raw':False,'external_article_reviewed':False,'verified_date_UTC':False,
        'case_parquet_sha256':core.digest(cp),'membership_parquet_sha256':core.digest(mp),
        'do_not_call_unreported_a_negative':True}
    core.write_json(out/'case_freeze_qc.json',report)
    return report

def manual_verify(source,manual_csv,out_dir):
    """Per-UUID manual evidence, require TWO different reviewers with corroborated URL/text.
    The source URL itself may be news (non-independent physically). Distinguish.
    """
    src=pd.read_parquet(source)
    review=pd.read_csv(manual_csv,dtype=str,keep_default_na=False)
    if not set(REVIEW_FIELDS)<=set(review):raise ValueError('Review file lacks actual audit evidence columns')
    if review.uuid.duplicated().any() or review.uuid.eq('').any():raise ValueError('Review UUID duplicates or blanks')
    if not set(review.uuid)<=set(src.uuid):raise ValueError('Review refers to unknown source UUID')
    for f in ('source_article_url','excerpt_confirms_flood_day','excerpt_confirms_locality','reviewer1','reviewer2','audit_date_utc'):
        if review[f].eq('').any():raise ValueError('Incomplete required independent manual field: '+f)
    if (review.reviewer1==review.reviewer2).any():raise ValueError('Two distinct reviewers required')
    if not review.source_article_url.str.startswith(('https://','http://')).all():raise ValueError('Source news URL must be real')
    if not ((review.reviewer1_verdict=='CONFIRMED_DAY_AND_LOCATION') &
            (review.reviewer2_verdict=='CONFIRMED_DAY_AND_LOCATION')).all():
        raise ValueError('Only mutually confirmed article events in publication verified set')
    if not review.audit_date_utc.map(core.day_str).notna().all():raise ValueError('Invalid audit dates')
    accepted=src.merge(review[REVIEW_FIELDS],on='uuid',how='inner',validate='one_to_one')
    cases,members=aggregate(accepted,kind='MANUAL_VERIFIED')
    out=pathlib.Path(out_dir)
    if out.exists() and any(out.iterdir()):raise FileExistsError('Immutable manual verified output exists')
    out.mkdir(parents=True,exist_ok=True)
    cases.to_parquet(out/'reported_grid_day_cases_MANUALLY_VERIFIED.parquet',index=False)
    members.to_parquet(out/'verified_uuid_lineage.parquet',index=False)
    report={'status':'ARTICLE_CONFIRMED_REPORTED_DAY_AND_LOCATION_NOT_PHYSICAL_FLOOD_TRUTH',
        'source_sha256':core.digest(source),'review_file_sha256':core.digest(manual_csv),
        'verified_source_uuids':len(accepted),'verified_grid_day_city_cases':len(cases),
        'verification_mode':'two reviewers + source news reference; time is local calendar day UTC proxy',
        'local_to_UTC_exact_time_unknown':True,'reporting_selection_bias_remains':True,
        'independent_physical_flood_validation':False}
    core.write_json(out/'verified_cases_qc.json',report)
    return report
