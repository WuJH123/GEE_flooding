"""Restartable Drive-backed global MERIT submission and scientific QC.

Cloud tasks run without this computer. All commands default to read-only;
`submit --execute` is the only command that starts new Earth Engine tasks.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import ee
import pandas as pd
import rasterio

from merit_direct_raster_pilot import HERE, ROOT, image
from native_merit_pilot import SELECTORS, build as native_build
from native_merit_pilot_audit import check_frame
from plan_merit_hybrid_v10 import GRID, MEMBERS, TASKS, REPORT, sha

sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, download, eeops, qc  # noqa: E402

DB = HERE / "merit_hybrid_v10.sqlite"
OUT = HERE / "merit_hybrid_qc"
FOLDER = "CEE_GF10_MERIT_HYBRID_V10_20261107"
SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
 task_key TEXT PRIMARY KEY, method TEXT NOT NULL, name TEXT NOT NULL UNIQUE,
 n_gf10 INTEGER NOT NULL, state TEXT NOT NULL, task_id TEXT, operation TEXT,
 gee_state TEXT, eecu_h REAL, source_sha TEXT NOT NULL, local_sha TEXT,
 error TEXT, updated_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transitions (
 updated_utc TEXT, task_key TEXT, old_state TEXT, new_state TEXT, detail TEXT);
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def change(conn: sqlite3.Connection, key: str, state: str, **kw) -> None:
    allowed = {"task_id", "operation", "gee_state", "eecu_h", "local_sha", "error"}
    if not set(kw) <= allowed:
        raise ValueError("Unapproved ledger update")
    old = conn.execute("SELECT state FROM jobs WHERE task_key=?", (key,)).fetchone()
    if old is None:
        raise KeyError(key)
    fields = ["state=?", "updated_utc=?"] + [f"{k}=?" for k in kw]
    conn.execute("UPDATE jobs SET " + ",".join(fields) + " WHERE task_key=?",
                 (state, now(), *kw.values(), key))
    conn.execute("INSERT INTO transitions VALUES(?,?,?,?,?)",
                 (now(), key, old[0], state, json.dumps(kw)))
    conn.commit()


def load_plan() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    report = json.loads(REPORT.read_text())
    if report["status"] != "FROZEN_GF10_PARTITION_QC_PASS_NO_GLOBAL_SUBMISSION":
        raise ValueError("Hybrid partition not frozen")
    for path, field in [(MEMBERS, "members_sha256"), (TASKS, "tasks_sha256"),
                        (GRID, "GF10_sha256")]:
        if sha(path) != report[field]:
            raise ValueError("Frozen MERIT source fingerprint changed: " + str(path))
    members = pd.read_parquet(MEMBERS)
    tasks = pd.read_csv(TASKS)
    if len(members) != 1395471 or len(tasks) != report["total_new_tasks"]:
        raise ValueError("MERIT plan membership/count drift")
    if members.grid_id.duplicated().any() or tasks.task_key.duplicated().any():
        raise ValueError("Duplicate MERIT grid or task key")
    if int(tasks.n_GF10.sum()) + report["pilot_submitted_GF10"] + 450 != len(members):
        raise ValueError("MERIT global coverage conservation failed")
    return members, tasks, report


def pilot_gate() -> dict:
    direct = {}
    for site in ("wuhan", "coast"):
        audit = json.loads((HERE / "merit_direct_pilots" / site / "audit.json").read_text())
        if audit.get("status") != "SCIENTIFIC_QC_PASS_DIRECT_RASTER_PILOT" or not audit.get("actual_eecu_h"):
            raise ValueError("Direct MERIT 60x60 real QC gate not passed: " + site)
        direct[site] = float(audit["actual_eecu_h"])
    west = json.loads((HERE / "merit_direct_pilots/westedge/audit.json").read_text())
    if west.get("GEE_state") != "FAILED" or "Reprojection output too large" not in west.get("error", ""):
        raise ValueError("West-edge direct failure not explicitly quarantined")
    native = {}
    for site in ("wuhan_weighted", "greenland_weighted", "westedge_weighted"):
        audit = json.loads((HERE / "native_merit_pilots" / site / "audit.json").read_text())
        if not audit.get("independent_raw_check", {}).get("source_pixel_tolerance_pass") or not audit.get("actual_EECU_h"):
            raise ValueError("Native weighted real source-pixel QC gate not passed: " + site)
        native[site] = float(audit["actual_EECU_h"])
    return {"direct_pilot_eecu_h": direct, "native_pilot_eecu_h": native,
            "westedge_direct_failure_quarantined": True}


def init() -> dict:
    _, tasks, report = load_plan()
    gate = pilot_gate()
    with db() as conn:
        for row in tasks.itertuples(index=False):
            conn.execute("INSERT OR IGNORE INTO jobs(task_key,method,name,n_gf10,state,source_sha,updated_utc) "
                         "VALUES(?,?,?,?,?,?,?)",
                         (row.task_key, row.method, "CEE_GF10_MERIT_HYBRID_V10_" + row.task_key,
                          int(row.n_GF10), "PLANNED", report["members_sha256"], now()))
        conn.commit()
        if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] != len(tasks):
            raise ValueError("Existing MERIT ledger conflicts with immutable plan")
    return {"status": "LEDGER_READY_NO_NEW_GEE_SUBMISSION", "tasks": len(tasks), "gate": gate}


def state_counts() -> dict:
    with db() as conn:
        return dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state").fetchall())


def reconcile(conn: sqlite3.Connection, remote: list[dict]) -> dict:
    by_name: dict[str, list[dict]] = {}
    for item in remote:
        by_name.setdefault(item.get("description", ""), []).append(item)
    updated = 0
    rows = conn.execute("SELECT * FROM jobs WHERE state NOT IN ('PLANNED','QC_PASS','QC_FAIL','QUARANTINED')").fetchall()
    for row in rows:
        matches = by_name.get(row["name"], [])
        if len(matches) != 1:
            raise RuntimeError(f"Uncertain submission intent {row['task_key']}: {len(matches)} remote matches")
        remote_task = matches[0]
        if row["task_id"] and remote_task.get("id") != row["task_id"]:
            raise RuntimeError("GEE task ID mismatch: " + row["task_key"])
        gee_state = remote_task.get("state")
        new = {"READY": "READY", "RUNNING": "RUNNING", "COMPLETED": "GEE_SUCCEEDED",
               "FAILED": "FAILED", "CANCELLED": "CANCELLED"}.get(gee_state)
        if not new:
            raise RuntimeError("Unexpected GEE state: " + str(gee_state))
        seconds = remote_task.get("batch_eecu_usage_seconds")
        if seconds is None and remote_task.get("name") and gee_state in ("COMPLETED", "FAILED", "CANCELLED"):
            operation = ee.data.getOperation(remote_task["name"])
            seconds = (operation.get("metadata") or {}).get("batchEecuUsageSeconds")
        eecu = float(seconds) / 3600 if seconds is not None else None
        if row["state"] != new or row["task_id"] is None or (eecu is not None and row["eecu_h"] is None):
            change(conn, row["task_key"], new, task_id=remote_task.get("id"),
                   operation=remote_task.get("name"), gee_state=gee_state,
                   eecu_h=eecu, error=remote_task.get("error_message"))
            updated += 1
    return {"updated": updated, "states": state_counts()}


def _wkt() -> str:
    return core.read_json(ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/config/recovery.json")["crs_wkt"]


def _task(ee_module, row, frame: pd.DataFrame, wkt: str):
    name = "CEE_GF10_MERIT_HYBRID_V10_" + row.task_key
    if row.method == "DIRECT_RASTER":
        x, y, width, height = map(int, (row.x0, row.y0, row.width, row.height))
        if width > 60 or height > 60 or width * height > 3600 or row.source_bbox_max > 50000:
            raise ValueError("Direct task outside live-verified envelope")
        bbox = [x * 10000, y * 10000, (x + width) * 10000, (y + height) * 10000]
        region = ee_module.Geometry.Rectangle(eeops.merit_export_interior(bbox),
                                              proj=wkt, geodesic=False)
        return ee_module.batch.Export.image.toDrive(
            image=image(ee_module, wkt).unmask(-9999), description=name, folder=FOLDER,
            fileNamePrefix=name, region=region, crs=wkt,
            crsTransform=[10000, 0, 0, 0, -10000, 0], maxPixels=width * height,
            fileFormat="GeoTIFF", formatOptions={"cloudOptimized": True, "noData": -9999})
    if row.method != "NATIVE_WEIGHTED" or len(frame) > 300:
        raise ValueError("Native weighted task outside pilot envelope")
    return ee_module.batch.Export.table.toDrive(
        collection=native_build(ee_module, "global_weighted", frame),
        description=name, folder=FOLDER, fileNamePrefix=name,
        fileFormat="CSV", selectors=SELECTORS)


def submit(execute: bool, batch_limit: int, budget_eecu: float,
           task_keys: list[str] | None = None) -> dict:
    members, tasks, _ = load_plan()
    gate = pilot_gate()
    if batch_limit < 1 or batch_limit > 1200 or budget_eecu > 900 or budget_eecu <= 0:
        raise ValueError("Unsafe batch/budget limit")
    with db() as conn:
        planned = set(r[0] for r in conn.execute("SELECT task_key FROM jobs WHERE state='PLANNED'"))
        selected = tasks[tasks.task_key.isin(planned)].copy()
        if task_keys:
            if len(task_keys) != len(set(task_keys)) or not set(task_keys) <= set(selected.task_key):
                raise ValueError("Named task absent, already submitted, or duplicated")
            selected = selected.set_index("task_key").loc[task_keys].reset_index()
            if len(selected) > batch_limit:
                raise ValueError("Named selection exceeds batch limit")
        else:
            selected["priority"] = selected.method.map({"DIRECT_RASTER": 0, "NATIVE_WEIGHTED": 1})
            selected = selected.sort_values(["priority", "task_key"]).head(batch_limit)
        if not execute:
            return {"status": "DRY_RUN_NO_GEE_SUBMISSION", "selected": len(selected),
                    "direct": int(selected.method.eq("DIRECT_RASTER").sum()),
                    "native": int(selected.method.eq("NATIVE_WEIGHTED").sum()),
                    "pilot_gate": gate, "first_keys": selected.task_key.head(10).tolist()}
        from budget_v10 import read as budget_read
        budget = budget_read()
        current = float(budget["non_double_counting_usage_indicator_eecu_h"])
        if current >= budget_eecu:
            raise RuntimeError("Project monthly EECU pause threshold reached")
        # 3x the highest observed per-cell pilot rate reserves for geography
        # variation. Monitoring is project-wide; no account quota is changed.
        rates = {"DIRECT_RASTER": max(gate["direct_pilot_eecu_h"].values()) / 3499,
                 "NATIVE_WEIGHTED": max(gate["native_pilot_eecu_h"].values()) / 300}
        ee.Initialize(project=core.PROJECT)
        remote = ee.data.getTaskList()
        reconcile(conn, remote)
        forecast = float(sum(3 * rates[r.method] * int(r.n_GF10)
                             for r in selected.itertuples(index=False)))
        committed = float(sum(3 * rates[r[0]] * int(r[1]) for r in conn.execute(
            "SELECT method,n_gf10 FROM jobs WHERE state IN "
            "('SUBMISSION_INTENT','SUBMITTED','READY','RUNNING','GEE_SUCCEEDED')")))
        if current + committed + forecast > budget_eecu:
            raise RuntimeError(f"Budget guard: {current:.2f}+{committed:.2f} committed+"
                               f"{forecast:.2f} new>{budget_eecu}")
        if any(x.get("state") in ("FAILED", "CANCELLED") for x in remote
               if str(x.get("description", "")).startswith("CEE_GF10_MERIT_HYBRID_V10_")):
            raise RuntimeError("Existing global MERIT task failed; stop new submission")
        names = {x.get("description") for x in remote}
        ready = sum(x.get("state") in ("READY", "RUNNING") for x in remote)
        if ready + len(selected) > 1800:
            raise RuntimeError("Bounded project cloud queue guard (1800)")
        groups = {key: frame for key, frame in members[members.task_key.isin(selected.task_key)]
                  .groupby("task_key", sort=False)}
        wkt = _wkt()
        submissions = []
        for row in selected.itertuples(index=False):
            name = "CEE_GF10_MERIT_HYBRID_V10_" + row.task_key
            if name in names:
                raise RuntimeError("Remote name already exists without local ledger: " + name)
            frame = groups[row.task_key]
            if len(frame) != int(row.n_GF10):
                raise ValueError("Task GF10 members changed: " + row.task_key)
            task = _task(ee, row, frame, wkt)
            change(conn, row.task_key, "SUBMISSION_INTENT")
            task.start()
            change(conn, row.task_key, "SUBMITTED", task_id=task.id)
            names.add(name)
            submissions.append({"task_key": row.task_key, "task_id": task.id,
                                "method": row.method, "n_GF10": int(row.n_GF10)})
            if len(submissions) % 25 == 0:
                print(json.dumps({"submission_progress": len(submissions),
                                  "selected": len(selected), "last_task_key": row.task_key}),
                      flush=True)
                live = ee.data.getTaskList()
                failures = [x for x in live if x.get("state") in ("FAILED", "CANCELLED")
                            and str(x.get("description", "")).startswith(
                                "CEE_GF10_MERIT_HYBRID_V10_")]
                if failures:
                    raise RuntimeError("GEE global MERIT failure during submission; "
                                       "stop before next batch: " +
                                       str([(x.get("id"), x.get("error_message")) for x in failures[:3]]))
                if len(submissions) % 100 == 0:
                    latest = budget_read()["non_double_counting_usage_indicator_eecu_h"]
                    if float(latest) >= budget_eecu:
                        raise RuntimeError("Project EECU pause threshold reached during submission")
        return {"status": "SUBMITTED_NOT_SCIENTIFICALLY_ACCEPTED",
                "submitted": submissions, "project_usage_indicator_eecu_h": current,
                "prior_unaccepted_commitment_3x_pilot_eecu_h": committed,
                "batch_3x_pilot_forecast_eecu_h": forecast}


def status(refresh: bool) -> dict:
    if not refresh:
        return {"status": "LOCAL_LEDGER_ONLY", "states": state_counts()}
    ee.Initialize(project=core.PROJECT)
    remote = ee.data.getTaskList()
    with db() as conn:
        rec = reconcile(conn, remote)
        costs = conn.execute("SELECT COUNT(*),COALESCE(SUM(eecu_h),0) FROM jobs WHERE eecu_h IS NOT NULL").fetchone()
    return {"status": "GEE_OPERATIONS_RECONCILED_NOT_SCIENCE_QC", "reconciliation": rec,
            "reported_task_cost_count": costs[0], "reported_task_eecu_h": costs[1]}


def recover_intent(key: str) -> dict:
    """Recover only an unstarted intent after two independent remote listings."""
    load_plan()
    ee.Initialize(project=core.PROJECT)
    name = "CEE_GF10_MERIT_HYBRID_V10_" + key
    tasks = ee.data.getTaskList()
    operations = ee.data.listOperations()
    task_matches = [item for item in tasks if item.get("description") == name]
    operation_matches = [item for item in operations if name in str(item)]
    if task_matches or operation_matches:
        raise RuntimeError("Remote task/operation exists; intent must be reconciled, not retried")
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE task_key=?", (key,)).fetchone()
        if row is None or row["state"] != "SUBMISSION_INTENT" or row["task_id"]:
            raise RuntimeError("Only an ID-less SUBMISSION_INTENT is recoverable")
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(row["updated_utc"])
        if age.total_seconds() < 30:
            raise RuntimeError("Wait for GEE listing consistency before recovering intent")
        evidence = {"task_key": key, "name": name, "time_utc": now(),
                    "intent_age_seconds": age.total_seconds(),
                    "getTaskList_count": len(tasks), "listOperations_count": len(operations),
                    "exact_remote_task_matches": 0, "operation_description_matches": 0,
                    "old_state": "SUBMISSION_INTENT", "new_state": "PLANNED",
                    "no_GEE_task_was_retried": True}
        core.write_json(HERE / ("intent_recovery_" + key + ".json"), evidence)
        change(conn, key, "PLANNED", error="INTENT_RECOVERED_NO_REMOTE_OPERATION")
    return evidence


def audit(limit: int) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("QC batch limit must be 1-100")
    members, tasks, _ = load_plan()
    ee.Initialize(project=core.PROJECT)
    remote = ee.data.getTaskList()
    with db() as conn:
        reconcile(conn, remote)
        rows = conn.execute("SELECT * FROM jobs WHERE state='GEE_SUCCEEDED' OR "
                            "(state='QC_FAIL' AND error='HAND low-elevation threshold fractions not nested') "
                            "ORDER BY task_key LIMIT ?",
                            (limit,)).fetchall()
        task_index = tasks.set_index("task_key")
        results = []
        OUT.mkdir(parents=True, exist_ok=True)
        for job in rows:
            key = job["task_key"]
            row = task_index.loc[key]
            frame = members.loc[members.task_key.eq(key)].copy()
            directory = OUT / key
            directory.mkdir(parents=True, exist_ok=True)
            try:
                if job["state"] == "QC_FAIL":
                    original = directory / "audit.json"
                    preserved = directory / "audit_initial_null_comparison_failure.json"
                    if not original.is_file():
                        raise ValueError("Cannot preserve original QC failure")
                    if not preserved.exists():
                        shutil.copy2(original, preserved)
                source = download.get_source(job["name"], directory, "drive",
                                             kind="merit" if job["method"] == "DIRECT_RASTER" else "weather")
                if source is None:
                    results.append({"task_key": key, "state": "GEE_SUCCEEDED_DRIVE_PENDING"})
                    continue
                if job["method"] == "DIRECT_RASTER":
                    expected = pd.Series({"crop_x0": int(row.x0), "crop_y0": int(row.y0),
                                          "width": int(row.width), "height": int(row.height),
                                          "n_land_cells": len(frame),
                                          "land_ids": ";".join(frame.grid_id.astype(str))})
                    quality = qc.merit(source, expected)
                    with rasterio.open(source) as ds:
                        data = ds.read(masked=True)
                    values = []
                    for cell in frame.itertuples(index=False):
                        xi = int(cell.grid_x) - int(row.x0)
                        yi = int(row.y0) + int(row.height) - int(cell.grid_y) - 1
                        values.append([str(cell.grid_id)] +
                                      [None if data.mask[i, yi, xi] else float(data[i, yi, xi])
                                       for i in range(16)])
                    output = pd.DataFrame(values, columns=["grid_id"] + core.BANDS)
                else:
                    output = pd.read_csv(source, dtype={"grid_id": "string"})
                    quality = check_frame(output, frame)
                    output = output.rename(columns={"hnd_p10": "merit_hand_p10_m",
                                                    "hnd_p50": "merit_hand_p50_m",
                                                    "hnd_p90": "merit_hand_p90_m",
                                                    "upa_max": "merit_upa_max_km2",
                                                    "upa_p90": "merit_upa_p90_km2"})
                    output["merit_upa_max_log1p"] = output.merit_upa_max_km2.clip(lower=0).map(__import__("math").log1p)
                    output = output[["grid_id"] + core.BANDS]
                if (len(output) != len(frame) or output.grid_id.duplicated().any() or
                    set(output.grid_id.astype(str)) != set(frame.grid_id.astype(str))):
                    raise ValueError("Frozen MERIT GF10 member mismatch")
                product = directory / "merit_QC_PASS.parquet"
                output.to_parquet(product, index=False)
                qc_report = {"status": "QC_PASS", "task_key": key, "n_GF10": len(frame),
                             "GEE_task_id": job["task_id"], "actual_eecu_h": job["eecu_h"],
                             "source_sha256": sha(source), "parquet_sha256": sha(product),
                             "quality": quality}
                core.write_json(directory / "audit.json", qc_report)
                change(conn, key, "QC_PASS", local_sha=sha(product))
                results.append({"task_key": key, "state": "QC_PASS", "n_GF10": len(frame)})
            except Exception as exc:
                core.write_json(directory / "audit.json", {"status": "QC_FAIL",
                                "task_key": key, "error": str(exc), "GEE_task_id": job["task_id"]})
                change(conn, key, "QC_FAIL", error=str(exc))
                results.append({"task_key": key, "state": "QC_FAIL", "error": str(exc)})
                break
    return {"status": "SCIENTIFIC_QC_BATCH_FINISHED", "results": results,
            "states": state_counts()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "status", "submit", "audit", "recover-intent"])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--batch-limit", type=int, default=10)
    parser.add_argument("--budget-eecu", type=float, default=900)
    parser.add_argument("--task-key", action="append")
    args = parser.parse_args()
    if args.command == "init":
        result = init()
    elif args.command == "status":
        result = status(args.refresh)
    elif args.command == "submit":
        result = submit(args.execute, args.batch_limit, args.budget_eecu, args.task_key)
    elif args.command == "recover-intent":
        if not args.task_key or len(args.task_key) != 1:
            raise ValueError("Provide exactly one --task-key for intent recovery")
        result = recover_intent(args.task_key[0])
    else:
        result = audit(args.batch_limit)
    print(json.dumps(result, indent=2, default=str))
