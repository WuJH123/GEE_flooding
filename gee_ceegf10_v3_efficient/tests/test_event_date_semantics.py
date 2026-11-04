import inspect
from ceeprodgee.ee_model import event_image

def test_utc_day_3hr_windows_no_previous_day_leakage_and_missing_is_masked():
    src=inspect.getsource(event_image)
    assert 'sequence(0,42)' in src
    assert 'updateMask(day.count().eq(48))' in src
    for n in (336,672,1440):
        assert f'.count().eq({n})' in src
    assert 'subtract(5).multiply(30)' not in src
