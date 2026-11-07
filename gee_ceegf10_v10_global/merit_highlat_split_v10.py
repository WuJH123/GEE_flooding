"""Recover failed high-lat MERIT parents by source-identical 30 km quadrants.

Every submission is recorded before task.start; existing names are never started twice.
The original 60 km task ledger is retained as failure/cancellation evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import ee
import pandas as pd
import rasterio

from merit_direct_raster_pilot import HERE, ROOT, image
from merit_hybrid_runner import DB
from plan_merit_hybrid_v10 import MEMBERS, REPORT, TASKS, sha

sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, download, eeops, qc  # noqa: E402

OUT = HERE / "merit_highlat_split_v10"
FOLDER = "CEE_GF10_MERIT_HIGHLAT_SPLIT_V10_20261108"
OLD_PILOT = HERE / "merit_split_highlat_probe"


def load(parent: str, quadrant: int):
    if quadrant not in (1, 2, 3, 4):
        raise ValueError("quadrant must be 1-4")
    report = core.read_json(REPORT)
    if sha(MEMBERS) != report["members_sha256"] or sha(TASKS) != report["tasks_sha256"]:
        raise ValueError("Frozen MERIT plan changed")
    tasks = pd.read_csv(TASKS).set_index("task_key")
    if parent not in tasks.index or tasks.loc[parent, "method"] != "DIRECT_RASTER":
        raise ValueError("Parent not in frozen direct MERIT plan")
    import sqlite3
    with sqlite3.connect(DB) as conn:
        state = conn.execute("SELECT state FROM jobs WHERE task_key=?", (parent,)).fetchone()
    if not state or state[0] not in ("FAILED", "CANCELLED"):
        raise ValueError("Parent has not failed/cancelled: " + parent)
    row = tasks.loc[parent]
    x = int(row.x0) + (30 if quadrant in (2, 4) else 0)
    y = int(row.y0) + (30 if quadrant in (3, 4) else 0)
    width = min(30, int(row.x0 + row.width) - x)
    height = min(30, int(row.y0 + row.height) - y)
    if width <= 0 or height <= 0:
        return None
    all_members = pd.read_parquet(MEMBERS, columns=["grid_id", "grid_x", "grid_y", "task_key"])
    frame = all_members.loc[all_members.task_key.eq(parent) &
                            all_members.grid_x.between(x, x + width - 1) &
                            all_members.grid_y.between(y, y + height - 1)].copy()
    if len(frame) == 0:
        return None
    if len(frame) > width * height or frame.grid_id.duplicated().any():
        raise ValueError("Invalid frozen quadrant membership")
    return frame, x, y, width, height


def paths(parent: str, quadrant: int):
    key = f"{parent}_Q{quadrant:02d}"
    # The first legacy pilot called the *upper-left* quadrant Q01. Keep its
    # record intact and use a distinct namespace for the frozen Q01..Q04 plan.
    name = (f"CEE_GF10_MERIT_SPLIT_V10_{key}" if key == "MD10_21_11_Q03"
            else f"CEE_GF10_MERIT_HLREC_V10_{key}")
    return key, OUT / key, name


def plan():
    """Freeze exact child ownership for failed/cancelled direct parents."""
    import sqlite3
    parent_rows = pd.read_csv(TASKS).set_index("task_key")
    with sqlite3.connect(DB) as conn:
        parents = [r[0] for r in conn.execute(
            "SELECT task_key FROM jobs WHERE method='DIRECT_RASTER' "
            "AND state IN ('FAILED','CANCELLED') ORDER BY task_key")]
    if not parents:
        raise ValueError("No eligible failed/cancelled parents")
    members = pd.read_parquet(MEMBERS, columns=["grid_id", "grid_x", "grid_y", "task_key"])
    expected = members.loc[members.task_key.isin(parents), ["grid_id", "task_key"]]
    rows, assigned = [], []
    for parent in parents:
        row = parent_rows.loc[parent]
        for quadrant in (1, 2, 3, 4):
            x = int(row.x0) + (30 if quadrant in (2, 4) else 0)
            y = int(row.y0) + (30 if quadrant in (3, 4) else 0)
            width = min(30, int(row.x0 + row.width) - x)
            height = min(30, int(row.y0 + row.height) - y)
            if width <= 0 or height <= 0:
                continue
            part = members.loc[members.task_key.eq(parent) &
                               members.grid_x.between(x, x + width - 1) &
                               members.grid_y.between(y, y + height - 1)]
            if part.empty:
                continue
            key, _, name = paths(parent, quadrant)
            rows.append({"split_key": key, "parent": parent, "quadrant": quadrant,
                         "x0": x, "y0": y, "width": width, "height": height,
                         "n_GF10": len(part), "name": name,
                         "pilot_reuse": parent == "MD10_-11_10" and quadrant == 3})
            assigned.extend(part.grid_id.astype(str))
    if len(assigned) != len(expected) or len(set(assigned)) != len(assigned) or \
       set(assigned) != set(expected.grid_id.astype(str)):
        raise ValueError("High-lat split GF10 partition does not conserve frozen IDs")
    result = pd.DataFrame(rows)
    if result.split_key.duplicated().any() or result.n_GF10.sum() != len(expected):
        raise ValueError("High-lat split task partition invalid")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "plan.csv"
    result.to_csv(path, index=False)
    report = {"status": "HIGH_LAT_SPLIT_PARTITION_QC_PASS_NO_NEW_GEE_SUBMISSION",
              "parent_tasks": len(parents), "split_tasks": len(result),
              "frozen_GF10": len(expected), "pilot_reuse_GF10": int(result.loc[result.pilot_reuse, "n_GF10"].sum()),
              "members_sha256": sha(MEMBERS), "source_tasks_sha256": sha(TASKS),
              "plan_sha256": sha(path)}
    core.write_json(OUT / "plan_report.json", report)
    return report


def submit(parent: str, quadrant: int, execute: bool):
    item = load(parent, quadrant)
    if item is None:
        return {"status": "EMPTY_QUADRANT", "parent": parent, "quadrant": quadrant}
    frame, x, y, width, height = item
    key, directory, name = paths(parent, quadrant)
    if parent == "MD10_-11_10" and quadrant == 3:
        # The first proven pilot occupies x=-660..-631,y=630..659.
        audit = core.read_json(OLD_PILOT / "audit.json")
        if audit.get("status") != "SCIENTIFIC_QC_PASS_30X30_HIGH_LAT":
            raise ValueError("Prior high-lat pilot is not accepted")
        return {"status": "REUSED_ACCEPTED_PILOT", "parent": parent,
                "quadrant": quadrant, "n_GF10": len(frame), "task_id": audit["task_id"]}
    preview = {"status": "DRY_RUN_NO_GEE_SUBMISSION", "key": key,
               "n_GF10": len(frame), "shape": [height, width], "x0": x, "y0": y}
    if not execute:
        return preview
    if (directory / "intent.json").exists():
        raise RuntimeError("Existing immutable split intent: " + key)
    ee.Initialize(project=core.PROJECT)
    if any(t.get("description") == name for t in ee.data.getTaskList()):
        raise RuntimeError("Identical split task already exists in GEE: " + name)
    wkt = core.read_json(ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/config/recovery.json")["crs_wkt"]
    bbox = [x * 10000, y * 10000, (x + width) * 10000, (y + height) * 10000]
    task = ee.batch.Export.image.toDrive(
        image=image(ee, wkt).unmask(-9999), description=name, folder=FOLDER,
        fileNamePrefix=name,
        region=ee.Geometry.Rectangle(eeops.merit_export_interior(bbox), proj=wkt, geodesic=False),
        crs=wkt, crsTransform=[10000, 0, 0, 0, -10000, 0], maxPixels=width * height,
        fileFormat="GeoTIFF", formatOptions={"cloudOptimized": True, "noData": -9999})
    directory.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(directory / "input_GF10.parquet", index=False)
    intent = {"status": "SUBMISSION_INTENT", "key": key, "parent": parent,
              "name": name, "x0": x, "y0": y, "width": width, "height": height,
              "n_GF10": len(frame), "input_sha256": core.sha(directory / "input_GF10.parquet")}
    core.write_json(directory / "intent.json", intent)
    task.start()
    intent.update(status="SUBMITTED_NOT_QC", task_id=task.id)
    core.write_json(directory / "intent.json", intent)
    return intent


def audit(parent: str, quadrant: int):
    item = load(parent, quadrant)
    if item is None:
        return {"status": "EMPTY_QUADRANT"}
    frame, x, y, width, height = item
    key, directory, name = paths(parent, quadrant)
    if parent == "MD10_-11_10" and quadrant == 3:
        return submit(parent, quadrant, False)
    intent = core.read_json(directory / "intent.json")
    if intent["name"] != name or core.sha(directory / "input_GF10.parquet") != intent["input_sha256"]:
        raise ValueError("Split intent/input fingerprint mismatch")
    ee.Initialize(project=core.PROJECT)
    matches = [t for t in ee.data.getTaskList() if t.get("description") == name]
    if len(matches) != 1 or matches[0]["id"] != intent.get("task_id"):
        raise ValueError("Split GEE operation cannot be uniquely reconciled")
    remote = matches[0]
    report = {"key": key, "task_id": remote["id"], "GEE_state": remote["state"],
              "n_GF10": len(frame), "status": "GEE_PENDING_OR_FAILED"}
    if remote["state"] == "COMPLETED":
        operation = ee.data.getOperation(remote["name"])
        seconds = (operation.get("metadata") or {}).get("batchEecuUsageSeconds")
        report["actual_eecu_h"] = float(seconds) / 3600 if seconds is not None else None
        source = download.get_source(name, directory, "drive", kind="merit")
        if source is None:
            report["status"] = "DRIVE_GEOTIFF_PENDING"
        else:
            try:
                expected = pd.Series({"crop_x0": x, "crop_y0": y, "width": width,
                                      "height": height, "n_land_cells": len(frame),
                                      "land_ids": ";".join(frame.grid_id.astype(str))})
                report["engineering_QC"] = qc.merit(source, expected)
                with rasterio.open(source) as ds:
                    data = ds.read(masked=True)
                values = []
                for cell in frame.itertuples(index=False):
                    xi = int(cell.grid_x) - x
                    yi = y + height - int(cell.grid_y) - 1
                    values.append([str(cell.grid_id)] +
                                  [None if data.mask[i, yi, xi] else float(data[i, yi, xi])
                                   for i in range(16)])
                output = pd.DataFrame(values, columns=["grid_id"] + core.BANDS)
                product = directory / "merit_QC_PASS.parquet"
                output.to_parquet(product, index=False)
                report.update(status="QC_PASS", source_sha256=core.sha(source),
                              parquet_sha256=core.sha(product))
            except Exception as exc:
                report.update(status="QC_FAIL", error=str(exc), source_sha256=core.sha(source))
    elif remote["state"] == "FAILED":
        report["error"] = remote.get("error_message")
    core.write_json(directory / "audit.json", report)
    return {k: v for k, v in report.items() if k != "engineering_QC"}


def batch_submit(limit: int, execute: bool):
    if not 1 <= limit <= 50:
        raise ValueError("One batch must contain 1-50 new tasks")
    report = core.read_json(OUT / "plan_report.json")
    if report["plan_sha256"] != sha(OUT / "plan.csv"):
        raise ValueError("Frozen high-lat recovery plan changed")
    candidates = pd.read_csv(OUT / "plan.csv")
    candidates = candidates.loc[~candidates.pilot_reuse.astype(bool)]
    candidates = candidates.loc[~candidates.split_key.map(lambda key: (OUT / key / "intent.json").exists())]
    chosen = candidates.head(limit)
    if not execute:
        return {"status": "DRY_RUN_NO_GEE_SUBMISSION", "selected": chosen.split_key.tolist(),
                "remaining_before": len(candidates)}
    ee.Initialize(project=core.PROJECT)
    remote = ee.data.getTaskList()
    failed = [t.get("description") for t in remote if
              (str(t.get("description", "")).startswith("CEE_GF10_MERIT_HLREC_V10_") or
               t.get("description") == "CEE_GF10_MERIT_SPLIT_V10_MD10_21_11_Q03") and
              t.get("state") == "FAILED"]
    if failed:
        raise RuntimeError("Existing high-lat split task failed; halt submission: " + str(failed[:5]))
    from budget_v10 import read as budget_read
    budget = budget_read()
    if budget["non_double_counting_usage_indicator_eecu_h"] >= 900:
        raise RuntimeError("Monthly 900 EECU-h submission pause reached")
    remote_names = {t.get("description") for t in remote}
    members = pd.read_parquet(MEMBERS, columns=["grid_id", "grid_x", "grid_y", "task_key"])
    wkt = core.read_json(ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/config/recovery.json")["crs_wkt"]
    metric_image = image(ee, wkt).unmask(-9999)
    submitted = []
    for row in chosen.itertuples(index=False):
        key, directory, name = paths(str(row.parent), int(row.quadrant))
        if directory.exists() or name in remote_names:
            raise RuntimeError("Existing local/remote split intent; cannot duplicate " + key)
        part = members.loc[members.task_key.eq(row.parent) &
                           members.grid_x.between(int(row.x0), int(row.x0 + row.width - 1)) &
                           members.grid_y.between(int(row.y0), int(row.y0 + row.height - 1))].copy()
        if len(part) != row.n_GF10 or part.grid_id.duplicated().any():
            raise ValueError("Frozen split membership drift: " + key)
        bbox = [int(row.x0) * 10000, int(row.y0) * 10000,
                int(row.x0 + row.width) * 10000, int(row.y0 + row.height) * 10000]
        task = ee.batch.Export.image.toDrive(
            image=metric_image, description=name, folder=FOLDER, fileNamePrefix=name,
            region=ee.Geometry.Rectangle(eeops.merit_export_interior(bbox), proj=wkt,
                                         geodesic=False),
            crs=wkt, crsTransform=[10000, 0, 0, 0, -10000, 0],
            maxPixels=int(row.width * row.height), fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": True, "noData": -9999})
        directory.mkdir(parents=True, exist_ok=False)
        part.to_parquet(directory / "input_GF10.parquet", index=False)
        intent = {"status": "SUBMISSION_INTENT", "key": key, "parent": str(row.parent),
                  "name": name, "x0": int(row.x0), "y0": int(row.y0),
                  "width": int(row.width), "height": int(row.height),
                  "n_GF10": len(part),
                  "input_sha256": core.sha(directory / "input_GF10.parquet")}
        core.write_json(directory / "intent.json", intent)
        task.start()
        intent.update(status="SUBMITTED_NOT_QC", task_id=task.id)
        core.write_json(directory / "intent.json", intent)
        remote_names.add(name)
        submitted.append({"key": key, "task_id": task.id})
    batch = {"status": "SUBMITTED_NOT_QC", "submitted": submitted,
             "project_usage_indicator_before_eecu_h": budget["non_double_counting_usage_indicator_eecu_h"],
             "remaining_after": len(candidates) - len(submitted)}
    core.write_json(OUT / f"batch_{len(list(OUT.glob('batch_*.json')))+1:03d}.json", batch)
    return batch


def batch_audit(limit: int):
    if not 1 <= limit <= 50:
        raise ValueError("Audit batch limit must be 1-50")
    rows = pd.read_csv(OUT / "plan.csv")
    results = []
    for row in rows.itertuples(index=False):
        directory = OUT / row.split_key
        if not (directory / "intent.json").exists():
            continue
        previous = directory / "audit.json"
        if previous.exists() and core.read_json(previous).get("status") == "QC_PASS":
            continue
        result = audit(str(row.parent), int(row.quadrant))
        results.append(result)
        if result.get("GEE_state") == "FAILED" or result.get("status") == "QC_FAIL":
            break
        if len(results) >= limit:
            break
    return {"audited": results,
            "QC_PASS": sum(x.get("status") == "QC_PASS" for x in results),
            "GEE_FAILED": sum(x.get("GEE_state") == "FAILED" for x in results)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["plan", "submit", "audit", "batch-submit", "batch-audit"])
    p.add_argument("--parent")
    p.add_argument("--quadrant", type=int)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--batch-limit", type=int, default=10)
    a = p.parse_args()
    if a.command == "plan":
        result = plan()
    elif a.command == "batch-submit":
        result = batch_submit(a.batch_limit, a.execute)
    elif a.command == "batch-audit":
        result = batch_audit(a.batch_limit)
    else:
        if a.parent is None or a.quadrant is None:
            p.error("submit/audit require --parent and --quadrant")
        result = submit(a.parent, a.quadrant, a.execute) if a.command == "submit" \
            else audit(a.parent, a.quadrant)
    print(json.dumps(result, indent=2))
