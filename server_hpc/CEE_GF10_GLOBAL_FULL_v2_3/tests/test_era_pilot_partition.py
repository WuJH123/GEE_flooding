from pathlib import Path

def test_era_pilot_and_full_output_names_are_disjoint():
    import inspect
    import ceeall.era as era
    code=inspect.getsource(era.run)
    assert "'era5ex_pilot' if max_rows is not None else 'era5ex'" in code
    assert "out=root/'data/derived/cee_all_v11'/kind/path.stem" in code


def test_gisd_pilot_staging_does_not_invalidate_parent_job():
    from ceeall.gisd import run
    import inspect
    source=inspect.getsource(run)
    assert "'expected_global_sources':953" in source
    assert "'source_inventory'" not in source
