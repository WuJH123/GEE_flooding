from pathlib import Path
import pytest
from ceeall.common import gf10_bounds,ensure_job,atomic_json,read_json

def test_negative_grid_index_remains_equal_area():
    assert gf10_bounds(-2,3)==(-20000,30000,-10000,40000)

def test_job_manifest_read_only_conflict(tmp_path):
    base=tmp_path/'task'
    first=ensure_job(base,{'product':'same','source':'a'})
    assert first==ensure_job(base,{'product':'same','source':'a'})
    with pytest.raises(ValueError):ensure_job(base,{'product':'other','source':'b'})

def test_atomic_json_write(tmp_path):
    f=tmp_path/'q.json'
    atomic_json(f,{'n':1})
    assert read_json(f)=={'n':1}
    assert not f.with_name('q.json.writing').exists()
