import pandas as pd
import pytest
from cee_recover.events import validate

def valid():
    return pd.DataFrame([
        dict(grid_id='1102_372',date_utc='2023-06-01',case_control='reported_case',pair_id='p1',storm_id='S101',city_id='C01',label_source='Groundsource_2026',sampling_protocol='blocked_spatiotemporal_exposure_v1'),
        dict(grid_id='1103_372',date_utc='2023-06-07',case_control='matched_unreported_exposure',pair_id='p1',storm_id='S102',city_id='C01',label_source='no_report_exposed_2023',sampling_protocol='blocked_spatiotemporal_exposure_v1')])

def grid():return pd.DataFrame({'grid_id':['1102_372','1103_372']})

def test_sealed_study_cohort_is_unlabeled_exposure_not_true_negative():
    z=validate(valid(),grid());assert len(z)==2
    assert set(z.case_control)=={'reported_case','matched_unreported_exposure'}

def test_no_report_can_never_be_called_verified_dry_control():
    z=valid();z.loc[1,'case_control']='no_flood'
    with pytest.raises(ValueError,match='verified non-flood'):validate(z,grid())

def test_old_grids_and_partial_metadata_stop_events():
    z=valid();z.loc[1,'grid_id']='old_20km'
    with pytest.raises(ValueError,match='GF10'):validate(z,grid())
    z=valid();z=z.drop(columns=['pair_id'])
    with pytest.raises(ValueError,match='Missing columns'):validate(z,grid())

def test_event_duplicates_not_silently_averaged():
    z=pd.concat([valid(),valid().iloc[[0]]],ignore_index=True)
    with pytest.raises(ValueError,match='Duplicate'):validate(z,grid())

def test_midday_time_not_valid_utc_calendar():
    z=valid();z.loc[0,'date_utc']='2023-06-01T13:30:00Z'
    with pytest.raises(ValueError,match='UTC'):validate(z,grid())

def test_unpaired_negative_not_valid_design():
    z=valid();z.loc[1,'pair_id']='p2'
    with pytest.raises(ValueError,match='pair_id'):validate(z,grid())
