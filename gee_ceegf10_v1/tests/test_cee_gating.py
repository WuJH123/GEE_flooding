import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathlib import Path
import ast
import pytest
from ceegee import models,grid


def test_science_contract_static_families_and_class_coding():
    assert models.STATIC_FAMILIES==('merit','worldcover')
    assert models.WORLD_CODES==(10,20,30,40,50,60,70,80,90,95,100)


def test_grid_bounds_match_frozen_zero_origin():
    assert grid.bounds_m(0,-1)==[0,-10000,10000,0]
    assert grid.bounds_m(-2,12)==[-20000,120000,-10000,130000]


def test_expected_grid_count_and_mass():
    assert grid.EXPECTED_CELLS==1_395_471
    assert abs(grid.EXPECTED_KM2-133095959.350)<1e-5


def test_models_do_not_leak_day_d_to_antecedent():
    source=(Path(models.__file__).read_text(encoding='utf8'))
    assert 'rain.filterDate(d.advance(-7,\'day\'),d)' in source
    assert 'rain.filterDate(d.advance(-30,\'day\'),d)' in source
    assert "filterDate(d.advance(-1,'day'),d)" in source
    assert 'imerg_rolling3h_max_mm' in source


def test_static_global_uses_multistage_reduction_with_strict_native_reducers():
    source=Path(models.__file__).read_text(encoding='utf8')
    assert source.count('bestEffort=False')>=4
    assert "[100,0,0,0,-100,0]" in source
    assert "[500,0,0,0,-500,0]" in source
    assert "setDefaultProjection" in source


def test_only_explicit_submit_can_create_tasks():
    from ceegee import cli
    source=Path(cli.__file__).read_text(encoding='utf8')
    assert source.count('task.start()')==1
    assert 'c.get(\'pilot_approved\')' in source
    assert 'first full-region stripe' in source.lower()
    assert 'refuse duplicate' in source.lower()
    assert 'create_root' in source
    assert 'batchEecuUsageSeconds' in source


def test_python_files_compile():
    root=Path(__file__).parents[1]
    for file in root.rglob('*.py'):
        ast.parse(file.read_text(encoding='utf8'))
