from pathlib import Path

def test_source_has_8_by_10_rectangular_audit_fix():
    repo=Path(__file__).resolve().parents[2]
    f=repo/'gee_ceegf10_v6_science_cohort'/'cee_v6'/'production.py'
    if not f.exists():
        import pytest
        pytest.skip('Run this integration test after GitHub monorepo merge')
    s=f.read_text(encoding='utf8')
    assert "check=qc.check_raster(p,'merit',xx,yy,expected_manifest=BANDS)" in s
    assert "(src.width,src.height,src.count)!=(w,h,16)" in s
