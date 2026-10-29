"""Local E-drive provenance checks, never network or GEE."""
from datetime import date
import json
import pandas as pd
import pytest
from gee_flooding.audit import inventory,summarize_labels

def test_inventory_is_local_only(tmp_path):
    root=tmp_path
    (root/"data/raw").mkdir(parents=True)
    (root/"data/raw/groundsource_2026.parquet").write_bytes(b"bad")
    # A corrupt claimed Parquet must be surfaced, not trusted from filename.
    with pytest.raises(Exception):
        inventory(root)
    (root/"data/raw/groundsource_2026.parquet").unlink()
    report=inventory(root)
    assert report["total_candidates"]>10
    qc=json.loads((root/"reports/qc/local_data_inventory.json").read_text(encoding="utf-8"))
    assert qc["status"]=="LOCAL_DISCOVERY_ONLY_NO_DOWNLOAD"
    assert next(x for x in qc["files"] if x["name"]=="new_groundsource_original")["exists_on_this_machine"] is False

def test_primary_news_summary_distinct_grid_days(tmp_path):
    labels=tmp_path/"labels.parquet"
    pd.DataFrame([
        ("a","0_0",date(2021,1,1),"HIGH_GEOCODE_SPECIFICITY"),
        ("b","0_0",date(2021,1,1),"HIGH_GEOCODE_SPECIFICITY"),
        ("c","1_0",date(2024,1,1),"HIGH_GEOCODE_SPECIFICITY"),
        ("d","1_0",date(2024,1,2),"MEDIUM_GEOCODE_SPECIFICITY"),
    ],columns=["event_id","grid_id","date","geocode_quality"]).to_parquet(labels,index=False)
    stats=summarize_labels(tmp_path,labels)
    assert stats["primary_rows"]==4
    assert stats["high_geocode_records"]==3
    assert stats["high_geocode_distinct_grid_days"]==2
    assert stats["high_geocode_distinct_grid_cells"]==2
    assert stats["high_geocode_records_2021_2025"]==3
    assert not (tmp_path/"cache/_label_distribution.sqlite").exists()

def test_duplicate_raw_event_id_rejected(tmp_path):
    labels=tmp_path/"dup.parquet"
    pd.DataFrame([
        ("a","0_0",date(2024,1,1),"HIGH_GEOCODE_SPECIFICITY"),
        ("a","1_0",date(2024,1,2),"HIGH_GEOCODE_SPECIFICITY")
    ],columns=["event_id","grid_id","date","geocode_quality"]).to_parquet(labels,index=False)
    with pytest.raises(ValueError,match="Duplicate raw event UUID"):
        summarize_labels(tmp_path,labels)
    assert not (tmp_path/"cache/_label_distribution.sqlite").exists()
