import pytest
import pandas as pd
from cee_v7 import core,gee

def test_gee_source_weather_has_complete_count_columns():
 assert 'imerg_n_obs_pre30d' in gee.CSV_FIELDS
 assert 'era5_soil_l1_prevday_m3m3' in gee.CSV_FIELDS
 assert 'imerg_rolling3h_max_mm' in gee.CSV_FIELDS

def test_gee_real_job_never_auto_submits_without_compliance(tmp_path):
 # No plans, no EE project credentials; dry-run must fail, not synthesize GEE data.
 with pytest.raises(FileNotFoundError):gee.select_request(tmp_path,'V7W_fake')

def test_source_day_proxy_is_not_verified_utc_date():
 assert core.PERMANENT_END=='2025-09-30'
 assert not core.run_conf('/tmp')['source_dates_are_utc_inferred']
