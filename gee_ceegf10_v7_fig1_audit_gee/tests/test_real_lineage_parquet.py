import importlib.util,pathlib
import pandas as pd
import pytest
from cee_v7 import builder,review,core
from cee_v7.geometry import parse_shape
pyarrow=pytest.importorskip('pyarrow')
import geopandas as gpd
import numpy as np
from shapely.geometry import box
from shapely import transform
from pyproj import Transformer

def generate(tmp_path):
 grid=tmp_path/'grid.parquet';pd.DataFrame([{'grid_id':'0_0','grid_x':0,'grid_y':0,'land_area_km2':100}]).to_parquet(grid)
 tr=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True)
 wgs=transform(box(3000,3000,6000,6000),lambda c:np.column_stack(tr.transform(c[:,0],c[:,1])))
 raw=tmp_path/'raw.parquet'
 pd.DataFrame([{'uuid':'U-EXACT','geometry':wgs.wkb,'start_date':'2022-07-20','end_date':'2022-07-20','area_km2':9.},
 {'uuid':'U-SPAN','geometry':wgs.wkb,'start_date':'2022-07-20','end_date':'2022-07-21','area_km2':9.}]).to_parquet(raw)
 tiers=tmp_path/'tiers.parquet';pd.DataFrame([
  dict(event_id=i,grid_id='0_0',date='2022-07-20',n_candidate_cells=1,primary_overlap=0.92,
       geocode_quality='HIGH_GEOCODE_SPECIFICITY',spatial_temporal_tier='A',tier_reason='synthetic',report_span_days=span)
   for i,span in [('U-EXACT',1),('U-SPAN',2)]]).to_parquet(tiers)
 ucdb=tmp_path/'ucdb.gpkg'
 gpd.GeoDataFrame({'ID_UC_G0':['CITY42']},geometry=[box(1000,1000,9000,9000)],crs='EPSG:6933').to_file(ucdb,driver='GPKG',layer='cities')
 return raw,tiers,grid,ucdb

def test_original_uuid_city_and_calendar_sources(tmp_path):
 raw,tiers,grid,ucdb=generate(tmp_path)
 result=builder.extract(raw,tiers,grid,ucdb,tmp_path/'source',strict_grid=False)
 assert result['provisional_uuid_rows']==1
 assert result['date_verified_per_uuid'] is False
 src=pd.read_parquet(tmp_path/'source'/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet')
 assert src.uuid.tolist()==['U-EXACT']
 assert src.city_id.tolist()==['CITY42']
 assert src.date_utc.tolist()==['2022-07-20']
 assert src.date_precision_verified.tolist()==[False]
 assert src.location_precision_verified.tolist()==[False]
 cases=review.create_cases(tmp_path/'source'/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet',tmp_path/'cases',review_n=1)
 assert cases['n_case_grid_days']==1
 assert not cases['verified_date_UTC']


def test_manual_promotion_requires_two_reviewers(tmp_path):
 raw,tiers,grid,ucdb=generate(tmp_path)
 builder.extract(raw,tiers,grid,ucdb,tmp_path/'source',strict_grid=False)
 src=tmp_path/'source'/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet'
 item={'uuid':'U-EXACT','source_article_url':'https://example.org/real-article',
 'excerpt_confirms_flood_day':'Event 20 July 2022','excerpt_confirms_locality':'Street X flooded',
 'reviewer1':'R1','reviewer2':'R1','reviewer1_verdict':'CONFIRMED_DAY_AND_LOCATION',
 'reviewer2_verdict':'CONFIRMED_DAY_AND_LOCATION','audit_date_utc':'2026-11-06',
 'evidence_kind':'news_article','independent_evidence_url':''}
 r=tmp_path/'review.csv';pd.DataFrame([item]).to_csv(r,index=False)
 with pytest.raises(ValueError,match='distinct'):review.manual_verify(src,r,tmp_path/'verified')
 item['reviewer2']='R2';pd.DataFrame([item]).to_csv(r,index=False)
 accepted=review.manual_verify(src,r,tmp_path/'verified')
 assert accepted['verified_grid_day_city_cases']==1
 assert accepted['independent_physical_flood_validation'] is False
