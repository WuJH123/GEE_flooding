"""Groundsource UUID -> original one-day claim -> frozen GF10 -> UCDB, no invented precision.

A product's one-day start=end is never equated to independent article verification.
Original Groundsource geometry is a *reported place* polygon, not inundation.
"""
from __future__ import annotations
import collections,csv,datetime as dt,pathlib
import pandas as pd
from . import core,geometry

RAW_COLS=['uuid','geometry','start_date','end_date','area_km2']
TIER_COLS=['event_id','grid_id','date','n_candidate_cells','primary_overlap',
           'geocode_quality','spatial_temporal_tier','tier_reason','report_span_days']
OUT_COLS=['uuid','source_raw_row','grid_id','grid_x','grid_y','city_id','date_utc',
 'source_local_date','date_temporal_evidence','utc_alignment','location_evidence',
 'location_precision_verified','date_precision_verified','raw_start_date','raw_end_date',
 'reported_area_km2','geocoded_area_km2','grid_geom_fraction','ucdb_geom_fraction',
 'ucdb_runnerup_fraction','geometry_type','source_geom_sha256','spatial_temporal_tier',
 'geocode_quality','tier_reason','label_source','city_method','source_article_url',
 'source_uuid_sha256','case_control','candidate_scope']


def load_tiers(path,allowed=('A',),max_cells=4,min_primary_overlap=0.8):
    import pyarrow.parquet as pq
    cols=set(pq.read_schema(path).names)
    if not set(TIER_COLS)<=cols:
        raise ValueError('Figure1 UUID-level tier columns missing: '+str(set(TIER_COLS)-cols))
    t=pd.read_parquet(path,columns=TIER_COLS)
    raw_rows=len(t)
    t['event_id']=t.event_id.astype('string')
    t['spatial_temporal_tier']=t.spatial_temporal_tier.astype('string').str.upper().str.strip()
    tier_code=t.spatial_temporal_tier.map(lambda s: str(s).split('_')[0] if pd.notna(s) else '')
    t=t[tier_code.isin(allowed)].copy()
    t=t[pd.to_numeric(t.n_candidate_cells,errors='coerce').between(1,max_cells)].copy()
    # Figure1 official code defines primary_overlap as a *numeric 0..1 fraction*,
    # NOT a Boolean. Its A tier is area<=25 km², overlap>=0.8,
    # n_candidate_cells<=4, report_span_days<=1 (source-text proxy only).
    overlap=pd.to_numeric(t.primary_overlap,errors='coerce')
    t=t[overlap.between(min_primary_overlap,1.0)].copy()
    t=t[t.geocode_quality.astype(str).eq('HIGH_GEOCODE_SPECIFICITY')].copy()
    # Multiple potentially conflicting intersections for one uuid must be quarantined,
    # not picked arbitrarily or expanded into multiple separate disasters.
    multiplicities=t.groupby('event_id',dropna=False).size()
    ambiguous=set(multiplicities.index[multiplicities.ne(1)].astype(str))
    t=t[~t.event_id.isin(ambiguous)].copy()
    if t.event_id.isna().any() or t.event_id.duplicated().any():raise ValueError('Duplicate tier UUID')
    if not len(t):raise ValueError('No source-level high-specificity records; inspect actual Figure1 tier values')
    return t.set_index('event_id',drop=False),{'raw_tier_rows':raw_rows,'eligible_tier_rows':len(t),
            'conflicting_uuid_groups':len(ambiguous),'allowed_tier_codes':list(allowed),'min_primary_overlap':min_primary_overlap,'high_geocode_required':True}


def extract(raw_path,tier_path,grid_path,city_gpkg,out_dir,city_field=None,city_layer=None,
            start='2021-01-01',end='2023-12-31',max_area_km2=25.,batch_size=30000,
            strict_grid=True,strict_raw_sha=None):
    import pyarrow as pa,pyarrow.parquet as pq
    out=pathlib.Path(out_dir)
    if out.exists() and any(out.iterdir()):raise FileExistsError('New empty output directory required: '+str(out))
    out.mkdir(parents=True,exist_ok=True)
    raw_sha=core.digest(raw_path)
    if strict_raw_sha and raw_sha!=strict_raw_sha:raise ValueError('Raw Groundsource SHA changed')
    tiers,ta=load_tiers(tier_path)
    grid=core.check_grid(grid_path,strict=strict_grid)
    # Stable join on the original Figure1 ID: no spatial/nearest-city inference.
    grididx=grid.set_index('grid_id')[['grid_x','grid_y']]
    cities=geometry.load_cities(city_gpkg,city_field,city_layer)
    rawpf=pq.ParquetFile(raw_path)
    if not set(RAW_COLS)<=set(rawpf.schema_arrow.names):raise ValueError('Official Groundsource raw columns missing')
    out_schema=pa.schema([(s,pa.int64() if s in ('source_raw_row','grid_x','grid_y')
                           else pa.float64() if s in ('reported_area_km2','geocoded_area_km2',
                                       'grid_geom_fraction','ucdb_geom_fraction','ucdb_runnerup_fraction')
                           else pa.bool_() if s in ('location_precision_verified','date_precision_verified')
                           else pa.string()) for s in OUT_COLS])
    path=out/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet'
    reject_path=out/'rejected_high_tier_uuid_reasons.csv'
    counts=collections.Counter();seen=set();writer=None;row_number=0
    with reject_path.open('w',newline='',encoding='utf8') as reject:
        fail=csv.DictWriter(reject,fieldnames=['uuid','reason','source_raw_row','raw_start_date','raw_end_date','tier_grid_id'])
        fail.writeheader()
        def rejected(uuid,reason,row,a,b,gid):
            counts['rejected_'+reason]+=1
            fail.writerow({'uuid':uuid,'reason':reason,'source_raw_row':row,'raw_start_date':a,
                           'raw_end_date':b,'tier_grid_id':gid})
        try:
            for rb in rawpf.iter_batches(batch_size=batch_size,columns=RAW_COLS):
                block=rb.to_pandas()
                uuids=block.uuid.astype(str)
                block['__rownum']=range(row_number,row_number+len(block))
                row_number+=len(block);counts['raw_seen']+=len(block)
                block=block.loc[uuids.isin(tiers.index)].copy()
                if block.empty:continue
                counts['raw_high_tier_found']+=len(block)
                block['__uuid']=block.uuid.astype(str)
                block=block.merge(tiers[TIER_COLS].drop(columns=['event_id']),
                                  left_on='__uuid',right_index=True,how='left',validate='many_to_one')
                rows=[]
                for r in block.itertuples(index=False,name=None):
                    a=dict(zip(block.columns,r));uid=a['__uuid'];gid=str(a['grid_id'])
                    sd=core.day_str(a['start_date']);ed=core.day_str(a['end_date']);td=core.day_str(a['date'])
                    if uid in seen:
                        rejected(uid,'DUPLICATE_RAW_UUID',a['__rownum'],sd,ed,gid);continue
                    seen.add(uid)
                    if not sd or not ed or sd!=ed or not start<=sd<=end or sd!=td:
                        rejected(uid,'NOT_SOURCE_SINGLE_DAY_OR_TIER_DATE_MISMATCH',a['__rownum'],sd,ed,gid);continue
                    if gid not in grididx.index:
                        rejected(uid,'NOT_IN_FROZEN_GF10',a['__rownum'],sd,ed,gid);continue
                    loc=grididx.loc[gid]
                    x=int(loc.grid_x);y=int(loc.grid_y)
                    value,reason=geometry.loc_assess(a['geometry'],x,y,cities,max_area_km2=max_area_km2)
                    if reason:
                        rejected(uid,reason,a['__rownum'],sd,ed,gid);continue
                    vals=dict(uuid=uid,source_raw_row=int(a['__rownum']),grid_id=gid,grid_x=x,grid_y=y,
                      city_id=str(value['city_id']),date_utc=sd,source_local_date=sd,
                      date_temporal_evidence='GROUNDSOURCE_SINGLE_DAY_TEXT_EXTRACTED_NOT_MANUALLY_VERIFIED',
                      utc_alignment='SOURCE_LOCAL_DAY_AS_UTC_CALENDAR_PROXY_NEEDS_UTC_SENSITIVITY',
                      location_evidence='GROUNDSOURCE_GEOCODED_PLACE_POLYGON_NOT_FLOOD_FOOTPRINT',
                      location_precision_verified=False,date_precision_verified=False,
                      raw_start_date=sd,raw_end_date=ed,
                      reported_area_km2=float(a['area_km2']) if pd.notna(a['area_km2']) else None,
                      geocoded_area_km2=value['geocoded_area_km2'],
                      grid_geom_fraction=value['grid_geom_fraction'],ucdb_geom_fraction=value['ucdb_geom_fraction'],
                      ucdb_runnerup_fraction=value['ucdb_runnerup_fraction'],geometry_type=value['geometry_type'],
                      source_geom_sha256=value['source_geom_sha256'],
                      spatial_temporal_tier=str(a['spatial_temporal_tier']),geocode_quality=str(a['geocode_quality']),
                      tier_reason=str(a['tier_reason']),label_source='Groundsource_2026_news_parquet',
                      city_method=value['city_method'],source_article_url=None,
                      source_uuid_sha256=core.stable_id(raw_sha,uid,n=64),case_control='reported_case',
                      candidate_scope='EXPOSURE_PREEXTRACTION_ONLY_NOT_INDEPENDENTLY_VERIFIED')
                    rows.append(vals)
                if rows:
                    table=pa.Table.from_pylist(rows,schema=out_schema)
                    if writer is None:writer=pq.ParquetWriter(path,out_schema,compression='zstd')
                    writer.write_table(table)
                    counts['provisional_accepted']+=len(rows)
        finally:
            if writer is not None:writer.close()
    if not path.exists():raise ValueError('No accepted source-specific UUIDs; inspect rejected reasons and city/tier mapping')
    report={'status':'SOURCE_DERIVED_REPORT_CASES_NOT_INDEPENDENTLY_VERIFIED',
       'source_sha256':raw_sha,'tiers_sha256':core.digest(tier_path),'gf10_sha256':core.digest(grid_path),
       'ucdb_sha256':core.digest(city_gpkg),'ucdb_layer':cities['layer'],'ucdb_field':cities['field'],
       'n_official_ucdb_cities':cities['n_cities'],'raw_total_rows':row_number,
       'provisional_uuid_rows':int(counts['provisional_accepted']),'tier_stats':ta,
       'rejection_counts':dict(counts),'date_source':'Groundsource extracted start/end, exact source-day only',
       'date_verified_per_uuid':False,'location_verified_per_uuid':False,
       'source_article_link_in_public_parquet':False,'utc_local_timezone_resolved':False,
       'location_polygon_is_inundation_area':False,'publication_ready':False,
       'groundsource_reference':core.PRODUCT,'output_parquet_sha256':core.digest(path)}
    core.write_json(out/'source_lineage_qc.json',report)
    return report
