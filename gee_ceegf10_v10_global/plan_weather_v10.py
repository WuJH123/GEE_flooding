"""Repack only unsubmitted GF10×UTC weather rows after a real 1000-row QC gate.

This is a read-only planner with respect to V3–V9 production directories. It
does not submit Earth Engine tasks or alter an existing SQLite task ledger.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(r"E:\GEE_flooding")
V8 = ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"
OUT = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
MAX_DATES = 3
MAX_ROWS = 1000


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def flush_group(groups: list[pd.DataFrame], rows: list[pd.DataFrame], tasks: list[dict]) -> None:
    if not groups:
        return
    block = pd.concat(groups, ignore_index=True)
    identity = "|".join((block.grid_id.astype(str) + "@" + block.date_utc.astype(str)).sort_values())
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    key = "W10_" + digest
    block["batch_id_v10"] = key
    rows.append(block)
    tasks.append({
        "batch_id": key,
        "n_rows": len(block),
        "n_dates": block.date_utc.nunique(),
        "date_min": str(block.date_utc.min()),
        "date_max": str(block.date_utc.max()),
        "grid_x_min": int(block.grid_x.min()),
        "grid_x_max": int(block.grid_x.max()),
        "grid_y_min": int(block.grid_y.min()),
        "grid_y_max": int(block.grid_y.max()),
        "science_contract": "IMERG_V07_PERMANENT_ERA5_LAND_PREVDAY_V3_FROZEN",
        "submission_state": "PLANNED_NOT_SUBMITTED",
    })


def main() -> None:
    source = V8 / "plans" / "weather_grid_days.parquet"
    original = pd.read_parquet(source)
    if len(original) != 275106 or original.duplicated(["grid_id", "date_utc"]).any():
        raise ValueError("Frozen V8 GF10×UTC candidate source changed")
    with sqlite3.connect(V8 / "reports" / "v8_production.sqlite") as db:
        accepted = {r[0] for r in db.execute(
            "SELECT key FROM jobs WHERE family='weather' AND state='ACCEPTED'")}
    old = original.loc[original.batch_id.isin(accepted)].copy()
    if len(old) != 4695:
        raise ValueError("Previously accepted V8 weather count changed")
    pilot_file = V8 / "reports" / "weather_1000_live_canary" / "expected_rows.parquet"
    pilot_qc_file = V8 / "reports" / "weather_1000_live_canary" / "audit.json"
    pilot_qc = json.loads(pilot_qc_file.read_text(encoding="utf-8"))
    if pilot_qc["status"] != "SCIENTIFIC_QC_PASS" or pilot_qc["QC"]["n_grid_dates"] != 1000:
        raise ValueError("Real 1000-row canary QC is absent")
    pilot = pd.read_parquet(pilot_file)[["grid_id", "date_utc"]]
    original_key = pd.MultiIndex.from_frame(original[["grid_id", "date_utc"]])
    pilot_key = pd.MultiIndex.from_frame(pilot)
    in_original = original_key.isin(pilot_key)
    pilot_source = original.loc[in_original].copy()
    if len(pilot_source) != 975 or set(pilot_source.batch_id) & accepted:
        raise ValueError("Canary planned-row overlap changed")
    remain = original.loc[~original.batch_id.isin(accepted) & ~in_original].copy()
    if len(old) + len(pilot_source) + len(remain) != len(original):
        raise ValueError("GF10×UTC source conservation failed")
    groups: list[pd.DataFrame] = []
    rows: list[pd.DataFrame] = []
    tasks: list[dict] = []
    current_n = 0
    for _, group in remain.sort_values(["date_utc", "grid_id"]).groupby("date_utc", sort=True):
        if len(group) > MAX_ROWS:
            raise ValueError("Single UTC day exceeds benchmarked row ceiling")
        if groups and (len(groups) >= MAX_DATES or current_n + len(group) > MAX_ROWS):
            flush_group(groups, rows, tasks)
            groups, current_n = [], 0
        groups.append(group)
        current_n += len(group)
    flush_group(groups, rows, tasks)
    packed = pd.concat(rows, ignore_index=True)
    batches = pd.DataFrame(tasks)
    if (len(packed) != len(remain) or packed.duplicated(["grid_id", "date_utc"]).any()
            or batches.batch_id.duplicated().any() or batches.n_rows.max() > MAX_ROWS
            or batches.n_dates.max() > MAX_DATES):
        raise ValueError("Optimized weather plan violates frozen identity or pilot size")
    if set(pd.MultiIndex.from_frame(packed[["grid_id", "date_utc"]])) != set(pd.MultiIndex.from_frame(remain[["grid_id", "date_utc"]])):
        raise ValueError("Optimized weather plan omitted or invented a GF10×UTC request")
    OUT.mkdir(exist_ok=True)
    rows_file = OUT / "weather_rows_v10.parquet"
    tasks_file = OUT / "weather_tasks_v10.csv"
    packed.to_parquet(rows_file, index=False)
    batches.to_csv(tasks_file, index=False)
    report = {
        "status": "PLANNED_NOT_SUBMITTED",
        "source_rows": len(original),
        "previously_accepted_v8_rows": len(old),
        "newly_accepted_1000_row_pilot_source_rows": len(pilot_source),
        "independent_v7_reference_rows_in_pilot": 25,
        "remaining_rows": len(remain),
        "optimized_remaining_tasks": len(batches),
        "max_rows_per_task": MAX_ROWS,
        "max_dates_per_task": MAX_DATES,
        "source_SHA256": sha(source),
        "pilot_csv_SHA256": pilot_qc["csv_sha256"],
        "rows_SHA256": sha(rows_file),
        "tasks_SHA256": sha(tasks_file),
        "no_GEE_submission": True,
    }
    (OUT / "weather_plan_qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
