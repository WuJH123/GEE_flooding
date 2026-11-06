import datetime as dt
import pytest
from cee_v7 import core

def test_day_is_calendar_not_arbitrary_timestamp():
 assert core.day_str('2021-07-20')=='2021-07-20'
 assert core.day_str('2021-02-30') is None
 assert core.day_str('2021-07-20 12:00:00') is None
 assert core.day_str(dt.datetime(2021,7,20,12)) is None
 assert core.day_str(dt.datetime(2021,7,20))=='2021-07-20'

def test_provenance_is_not_independent_verification():
 v=core.run_conf('/tmp/v7')
 assert v['physical_flood_truth'] is False
 assert v['source_dates_are_utc_inferred'] is False
 assert v['output_cells_are_source_geocode_not_inundation'] is True

def test_immutable_reports(tmp_path):
 p=tmp_path/'qc.json'
 core.write_json(p,{'status':'A'})
 with pytest.raises(FileExistsError):core.write_json(p,{'status':'B'})
 assert core.read_json(p)['status']=='A'

def test_project_rejects_unapproved_projects():
 with pytest.raises(ValueError):core.assert_project('other-project')
 core.assert_project(core.PROJECT)
