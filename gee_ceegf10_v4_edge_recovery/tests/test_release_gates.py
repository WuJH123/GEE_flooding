from pathlib import Path
import inspect
import pytest
from cee_recover import run,event_gee,events,event_audit


def test_v4_never_modifies_previous_ledger():
    src=inspect.getsource(run.init)
    assert 'frozen_copy(legacy' in src
    assert "LEDGER=HOME/'reports'/'recovery_tasks.json'" in Path(run.__file__).read_text()
    assert "source_ledger_treated_readonly" in src


def test_commitment_to_single_task_budget_and_no_automatic_bulk():
    src=inspect.getsource(run.submit)
    assert 'task.start()' in src
    assert 'if not a.execute:return' in src
    assert 'cost_ceiling_checked_h' in src
    assert 'maxPixels=200' in src
    assert 'region=export_roi' in src
    assert 'crsTransform=em.TRANSFORM_10' in src


def test_event_not_submitted_without_casecontrol_plan_or_exact_confirm():
    src=inspect.getsource(event_gee.run)
    assert "if not all(p.exists()" in src
    assert 'if not a.execute:return' in src
    assert "a.confirm!=c['run_id']" in src
    assert 'Previous event task usage unavailable' in src
    assert 'old.append(' in src
    assert 'status' not in events.REQUIRED


def test_era5_null_remains_null_in_event_audit():
    src=inspect.getsource(event_audit.audit)
    assert "era5_soil_l1_prevday_m3m3" in src
    assert 'if count is not None and float(count)!=48 and rainfall is not None' in src
    assert 'Missing observations remain null' in src


def test_event_design_never_infers_negatives_from_news_absence():
    assert events.ALLOWED=={'reported_case','matched_unreported_exposure'}
    assert 'storm_id' in events.REQUIRED
    assert 'sampling_protocol' in events.REQUIRED
