"""Bounded, restartable GEE production for the verified 1000-row weather plan.

Default command is read-only ``status``.  Only ``run --execute`` starts tasks.
The scientific expression is loaded from the unchanged V3 ee_model.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd


ROOT = Path(r"E:\GEE_flooding")
V8 = ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"
HERE = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
sys.path.insert(0, str(V8))
from cee_v8 import budget_v9, core, download, eeops, qc  # noqa: E402

DB = HERE / "weather_v10.sqlite"
ROWS = HERE / "weather_rows_v10.parquet"
TASKS = HERE / "weather_tasks_v10.csv"
PLAN_QC = HERE / "weather_plan_qc.json"
DOWNLOADS = HERE / "downloads"
NAME_PREFIX = "CEE_GF10_WEATHER_V10_20261106_"
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 key TEXT PRIMARY KEY, state TEXT NOT NULL, task_id TEXT, operation TEXT,
 name TEXT NOT NULL UNIQUE, n_rows INTEGER NOT NULL, source_sha TEXT NOT NULL,
 eecu_h REAL, local_sha TEXT, error TEXT, updated_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_weather_v10_state ON jobs(state);
CREATE TABLE IF NOT EXISTS transitions (
 ts_utc TEXT NOT NULL, key TEXT NOT NULL, old_state TEXT, new_state TEXT,
 details TEXT);
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def database() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


def transition(conn: sqlite3.Connection, key: str, new: str, **kw) -> None:
    old = conn.execute("SELECT state FROM jobs WHERE key=?", (key,)).fetchone()
    if old is None:
        raise KeyError(key)
    if any(k not in {"task_id", "operation", "eecu_h", "local_sha", "error"} for k in kw):
        raise ValueError("Illegal task ledger field")
    cols = ["state=?", "updated_utc=?"]
    args = [new, now()]
    for k, v in kw.items():
        cols.append(k + "=?")
        args.append(v)
    conn.execute("UPDATE jobs SET " + ",".join(cols) + " WHERE key=?", (*args, key))
    conn.execute("INSERT INTO transitions VALUES(?,?,?,?,?)",
                 (now(), key, old[0], new, json.dumps(kw)))
    conn.commit()


def validate_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    report = json.loads(PLAN_QC.read_text(encoding="utf-8"))
    if report["status"] != "PLANNED_NOT_SUBMITTED" or not report["no_GEE_submission"]:
        raise ValueError("Untrusted v10 weather plan")
    if core.sha(ROWS) != report["rows_SHA256"] or core.sha(TASKS) != report["tasks_SHA256"]:
        raise ValueError("Weather plan hash mismatch")
    data = pd.read_parquet(ROWS)
    tasks = pd.read_csv(TASKS)
    if len(data) != report["remaining_rows"] or len(tasks) != report["optimized_remaining_tasks"]:
        raise ValueError("Weather plan count mismatch")
    if data.duplicated(["grid_id", "date_utc"]).any():
        raise ValueError("GF10×UTC duplicate in new plan")
    if len(data.groupby("batch_id_v10")) != len(tasks):
        raise ValueError("Batch count mismatch")
    return data, tasks


def init() -> dict:
    _, tasks = validate_inputs()
    source_sha = core.sha(ROWS)
    with database() as conn:
        n_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        for row in tasks.itertuples(index=False):
            conn.execute("INSERT OR IGNORE INTO jobs(key,state,name,n_rows,source_sha,updated_utc) "
                         "VALUES(?,?,?,?,?,?)",
                         (row.batch_id, "PLANNED", NAME_PREFIX + row.batch_id,
                          int(row.n_rows), source_sha, now()))
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if n != len(tasks):
            raise ValueError("Existing task ledger does not match frozen plan")
    return {"status": "LEDGER_INITIALIZED_NO_GEE_SUBMISSION", "n_jobs": n,
            "existing_jobs": n_before}


def build_weather_1000(ee, members: pd.DataFrame, wkt: str):
    if len(members) > 1000 or members.date_utc.nunique() > 3:
        raise ValueError("Task exceeds live-validated envelope")
    model = eeops.model_from_local(ROOT)
    components = []
    for day, group in members.groupby("date_utc", sort=True):
        features = [ee.Feature(eeops.rect(ee, int(z.grid_x), int(z.grid_y), wkt),
                               {"grid_id": str(z.grid_id), "date_utc": str(day)})
                    for z in group.itertuples(index=False)]
        collection = ee.FeatureCollection(features)
        components.append(model.event_image(ee, str(day)).reduceRegions(
            collection=collection, reducer=ee.Reducer.mean(),
            crs="EPSG:4326", scale=11132, tileScale=4))
    return ee.FeatureCollection(components).flatten()


def reconcile(conn: sqlite3.Connection, ee, remote: list[dict]) -> dict:
    changed = 0
    by_name: dict[str, list[dict]] = {}
    for task in remote:
        by_name.setdefault(task.get("description", ""), []).append(task)
    for row in conn.execute("SELECT * FROM jobs WHERE state NOT IN ('PLANNED','ACCEPTED','QUARANTINED')"):
        matches = by_name.get(row["name"], [])
        if len(matches) != 1:
            raise RuntimeError(f"Uncertain GEE intent {row['key']}: {len(matches)} exact operations; no new submissions")
        task = matches[0]
        if row["task_id"] and task.get("id") != row["task_id"]:
            raise RuntimeError("Task ID conflict: " + row["key"])
        remote_state = task.get("state")
        mapped = {"READY": "READY", "RUNNING": "RUNNING", "COMPLETED": "GEE_SUCCEEDED",
                  "FAILED": "FAILED", "CANCELLED": "FAILED"}.get(remote_state)
        if mapped is None:
            raise RuntimeError("Unknown GEE operation state: " + str(remote_state))
        sec = task.get("batch_eecu_usage_seconds")
        if sec is None and task.get("name"):
            op = ee.data.getOperation(task["name"])
            sec = (op.get("metadata") or {}).get("batchEecuUsageSeconds")
        eecu = float(sec) / 3600 if sec is not None else None
        if row["state"] != mapped or row["task_id"] is None or (eecu is not None and row["eecu_h"] is None):
            transition(conn, row["key"], mapped, task_id=task.get("id"),
                       operation=task.get("name"), eecu_h=eecu,
                       error=task.get("error_message"))
            changed += 1
    return {"reconciled": changed}


def _drive_index() -> tuple[object, dict[str, dict]]:
    """One Drive listing for a QC batch; no per-task search or local CSV."""
    session = download._drive_session()
    response = session.get("https://www.googleapis.com/drive/v3/files", params={
        "q": f"name contains '{NAME_PREFIX}' and trashed = false",
        "fields": "nextPageToken,files(id,name,size,md5Checksum)", "pageSize": 1000,
    }, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("nextPageToken"):
        raise RuntimeError("Drive result listing exceeded 1000; paginate before continuing")
    index = {}
    for item in payload.get("files", []):
        if item["name"] in index:
            raise RuntimeError("Duplicate Drive CSV name: " + item["name"])
        index[item["name"]] = item
    return session, index


def _check_weather_frame(actual: pd.DataFrame, expected: pd.DataFrame) -> dict:
    """Scientific QC on CSV bytes already read from Drive into memory."""
    if not set(core.FIELDS) <= set(actual):
        raise ValueError("GEE weather CSV missing required frozen fields")
    actual = actual.copy()
    actual.grid_id = actual.grid_id.astype(str)
    actual.date_utc = actual.date_utc.astype(str)
    if actual.duplicated(["grid_id", "date_utc"]).any():
        raise ValueError("Duplicate GF10×UTC in GEE CSV")
    actual_pairs = set(zip(actual.grid_id, actual.date_utc))
    expected_pairs = set(zip(expected.grid_id.astype(str), expected.date_utc.astype(str)))
    if len(actual) != len(expected) or actual_pairs != expected_pairs:
        raise ValueError("GEE CSV missing, duplicated, or invented GF10×UTC rows")
    for band in core.FIELDS[2:]:
        actual[band] = pd.to_numeric(actual[band], errors="coerce")
    counts = {"imerg_n_obs_day": 48, "imerg_n_obs_pre7d": 336,
              "imerg_n_obs_pre14d": 672, "imerg_n_obs_pre30d": 1440}
    complete = pd.Series(True, index=actual.index)
    for band, n in counts.items():
        complete &= actual[band].eq(n)
    rain = ["imerg_day_mm", "imerg_peak_30min_mm_h", "imerg_rolling3h_max_mm", "imerg_pre7d_mm",
            "imerg_pre14d_mm", "imerg_pre30d_mm"]
    complete &= actual[rain].notna().all(axis=1) & actual[rain].ge(-0.001).all(axis=1)
    complete &= actual.imerg_rolling3h_max_mm.le(actual.imerg_day_mm + 0.01)
    complete &= actual.imerg_rolling3h_max_mm.ge(actual.imerg_peak_30min_mm_h * 0.5 - 0.01)
    complete &= actual.imerg_pre7d_mm.le(actual.imerg_pre14d_mm + 0.01)
    complete &= actual.imerg_pre14d_mm.le(actual.imerg_pre30d_mm + 0.01)
    if not bool(complete.all()):
        raise ValueError(f"Incomplete/implausible IMERG in {int((~complete).sum())}/{len(actual)} rows; no zero fill")
    soil = actual[["era5_soil_l1_prevday_m3m3", "era5_soil_l2_prevday_m3m3"]]
    era = (soil.notna().all(axis=1) & soil.ge(-0.001).all(axis=1)
           & soil.le(1.001).all(axis=1) & actual.era5_t2m_prevday_C.between(-90, 65))
    return {"n_rows": len(actual), "IMERG_complete_rows": int(complete.sum()),
            "ERA5_missing_or_invalid_rows": int((~era).sum()),
            "missing_per_band": {band: int(actual[band].isna().sum())
                                 for band in core.FIELDS[2:]},
            "source_dates_not_independently_verified": True,
            "news_absence_is_not_flood_absence": True}


def audit_successes(conn: sqlite3.Connection, data: pd.DataFrame, force: bool = False) -> dict:
    pending = conn.execute("SELECT * FROM jobs WHERE state='GEE_SUCCEEDED' ORDER BY key LIMIT 10").fetchall()
    if not pending or (len(pending) < 10 and not force):
        return {"newly_accepted": 0, "drive_qc_backlog": len(pending)}
    if any(row["eecu_h"] is None for row in pending):
        return {"newly_accepted": 0, "drive_qc_backlog": len(pending), "reason": "EECU_REPORT_PENDING"}
    session, file_index = _drive_index()
    for row in pending:
        if row["name"] + ".csv" not in file_index:
            return {"newly_accepted": 0, "drive_qc_backlog": len(pending),
                    "reason": "DRIVE_FILE_PENDING:" + row["key"]}
    frames = []
    manifest = []
    for row in pending:
        item = file_index[row["name"] + ".csv"]
        response = session.get(f"https://www.googleapis.com/drive/v3/files/{item['id']}",
                               params={"alt": "media"}, timeout=120)
        response.raise_for_status()
        raw = response.content
        csv_sha = hashlib.sha256(raw).hexdigest()
        expected = data.loc[data.batch_id_v10.eq(row["key"])]
        try:
            frame = pd.read_csv(io.BytesIO(raw), dtype={"grid_id": "string", "date_utc": "string"})
            quality = _check_weather_frame(frame, expected)
        except Exception as exc:
            transition(conn, row["key"], "QUARANTINED",
                       error=type(exc).__name__ + ": " + str(exc)[:800])
            return {"newly_accepted": 0, "drive_qc_backlog": len(pending),
                    "science_failure": row["key"]}
        for band in core.FIELDS[2:]:
            frame[band] = pd.to_numeric(frame[band], errors="coerce")
        frame["batch_id_v10"] = row["key"]
        frames.append(frame)
        manifest.append({"key": row["key"], "csv_sha256": csv_sha,
                         "eecu_h": row["eecu_h"], "quality": quality})
    fingerprint = hashlib.sha256("|".join(sorted(x["key"] for x in manifest)).encode()).hexdigest()[:16]
    dest = HERE / "parquet_batches" / ("weather_" + fingerprint + ".parquet")
    dest.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(frames, ignore_index=True)
    if combined.duplicated(["grid_id", "date_utc"]).any():
        raise ValueError("Cross-task GF10×UTC duplicate in QC batch")
    if dest.exists():
        old = pd.read_parquet(dest)
        if len(old) != len(combined) or set(old.batch_id_v10) != set(x["key"] for x in manifest):
            raise RuntimeError("Existing QC batch path conflicts with current source")
    else:
        tmp = dest.with_suffix(".parquet.part")
        combined.to_parquet(tmp, index=False)
        os.replace(tmp, dest)
    batch_sha = core.sha(dest)
    core.write_json(dest.with_suffix(".qc.json"), {
        "status": "BATCH_SCIENTIFIC_QC_PASS", "n_rows": len(combined),
        "n_tasks": len(manifest), "parquet_sha256": batch_sha,
        "source_csv_and_EECU": manifest})
    for item in manifest:
        transition(conn, item["key"], "ACCEPTED", local_sha=item["csv_sha256"])
    return {"newly_accepted": len(manifest), "drive_qc_backlog": 0,
            "accepted_parquet": str(dest)}


def tick(execute: bool = False, max_active: int = 2, budget_eecu: float = 900) -> dict:
    if max_active not in (1, 2) or budget_eecu > 900:
        raise ValueError("Unapproved concurrency or monthly budget")
    data, _ = validate_inputs()
    init()
    if not execute:
        with database() as conn:
            states = dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state").fetchall())
        return {"status": "DRY_RUN_NO_GEE_SUBMISSION", "states": states}
    download.check_auth("drive")
    ee = eeops.initialize()
    remote = ee.data.getTaskList()
    with database() as conn:
        rec = reconcile(conn, ee, remote)
        pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='GEE_SUCCEEDED'").fetchone()[0]
        planned = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='PLANNED'").fetchone()[0]
        active_before_qc = conn.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('SUBMISSION_INTENT','READY','RUNNING')").fetchone()[0]
        audited = audit_successes(conn, data, force=(pending >= 10 or (planned == 0 and active_before_qc == 0)))
        bad = conn.execute("SELECT key,state,error FROM jobs WHERE state IN ('FAILED','QUARANTINED') LIMIT 1").fetchone()
        if bad:
            return {"status": "FAILED_OR_SCIENCE_QUARANTINED_PAUSE", "task": dict(bad), **rec, **audited}
        active = conn.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('SUBMISSION_INTENT','READY','RUNNING')").fetchone()[0]
        awaiting = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='GEE_SUCCEEDED'").fetchone()[0]
        if awaiting >= 10:
            return {"status": "QC_BATCH_WAIT", "awaiting_drive_qc": awaiting, **rec, **audited}
        usage = budget_v9.current_month_eecu_hours(core.PROJECT)
        budget = budget_v9.budget_decision(usage, limit=budget_eecu, simultaneous=max_active)
        if not budget["can_submit"]:
            return {"status": "MONTHLY_BUDGET_PAUSE", "budget": budget, **rec, **audited}
        free = max(0, max_active - active)
        if free == 0:
            return {"status": "AT_CONCURRENCY_CAP", "active": active, **rec, **audited}
        candidates = conn.execute("SELECT * FROM jobs WHERE state='PLANNED' ORDER BY key LIMIT ?", (free,)).fetchall()
        if not candidates:
            n = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='ACCEPTED'").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            return {"status": "ALL_WEATHER_V10_ACCEPTED" if n == total else "WAITING_FOR_QC",
                    "accepted_tasks": n, "total_tasks": total, **rec, **audited}
        wkt = core.read_json(core.root_files(ROOT)["v4"] / "config" / "recovery.json")["crs_wkt"]
        by_name = {x.get("description") for x in remote}
        submitted = []
        for row in candidates:
            if row["name"] in by_name:
                raise RuntimeError("GEE name already exists: " + row["name"])
            members = data.loc[data.batch_id_v10.eq(row["key"])]
            if len(members) != row["n_rows"]:
                raise ValueError("Batch membership changed")
            collection = build_weather_1000(ee, members, wkt)
            task = ee.batch.Export.table.toDrive(collection=collection,
                description=row["name"], folder=core.RUN, fileNamePrefix=row["name"],
                fileFormat="CSV", selectors=core.FIELDS)
            # Commit intent before task.start(). A crash between the two is
            # reconciled by exact unique GEE description and never blind retry.
            transition(conn, row["key"], "SUBMISSION_INTENT")
            task.start()
            transition(conn, row["key"], "READY", task_id=task.id,
                       operation=f"projects/{core.PROJECT}/operations/{task.id}")
            submitted.append({"key": row["key"], "task_id": task.id})
        return {"status": "SUBMITTED_NOT_SCIENTIFICALLY_ACCEPTED", "submitted": submitted,
                "project_month_conservative_eecu_h": budget["project_eecu_h"], **rec, **audited}


def loop(max_active: int = 2, budget_eecu: float = 900, poll_seconds: int = 90) -> None:
    from google.auth.exceptions import TransportError
    from requests.exceptions import RequestException
    if poll_seconds < 30:
        raise ValueError("Avoid excessive GEE polling")
    transient = 0
    while True:
        try:
            result = tick(True, max_active=max_active, budget_eecu=budget_eecu)
            transient = 0
        except (ConnectionError, TimeoutError, OSError, TransportError, RequestException) as exc:
            transient += 1
            if transient > 8:
                raise
            wait = min(300, 15 * 2 ** (transient - 1))
            print(json.dumps({"status": "NETWORK_RETRY_NO_NEW_SUBMISSION",
                              "error": str(exc)[:300], "seconds": wait}), flush=True)
            time.sleep(wait)
            continue
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result["status"] in ("ALL_WEATHER_V10_ACCEPTED", "FAILED_OR_SCIENCE_QUARANTINED_PAUSE",
                                "MONTHLY_BUDGET_PAUSE"):
            return
        time.sleep(poll_seconds)


def submit_all_once(budget_eecu: float = 900) -> dict:
    """One-time durable submission; EE runs queued tasks after this process exits.

    No resident local scheduler, downloads, or QC are performed here. This is
    only valid because the entire 378-task plan is below the official 3000
    READY queue and a 2x observed-max cost envelope is below the budget fuse.
    """
    if budget_eecu > 900:
        raise ValueError("Monthly budget fuse cannot exceed 900 EECU-h")
    data, tasks = validate_inputs()
    init()
    ee = eeops.initialize()
    remote = ee.data.getTaskList()
    active_remote = sum(x.get("state") in ("READY", "RUNNING") for x in remote)
    with database() as conn:
        rec = reconcile(conn, ee, remote)
        bad = conn.execute("SELECT key,state,error FROM jobs WHERE state IN ('FAILED','QUARANTINED') LIMIT 1").fetchone()
        if bad:
            raise RuntimeError("Existing failed science task blocks bulk submission: " + str(dict(bad)))
        uncertain = conn.execute("SELECT key FROM jobs WHERE state='SUBMISSION_INTENT' LIMIT 1").fetchone()
        if uncertain:
            raise RuntimeError("Unreconciled task intent blocks submission: " + uncertain[0])
        planned = conn.execute("SELECT * FROM jobs WHERE state='PLANNED' ORDER BY key").fetchall()
        if active_remote + len(planned) > 3000:
            raise RuntimeError("Official 3000 READY queue cap would be exceeded")
        usage = budget_v9.current_month_eecu_hours(core.PROJECT)
        budget = budget_v9.budget_decision(usage, limit=budget_eecu, simultaneous=2)
        if not budget["can_submit"]:
            raise RuntimeError("Live project monthly budget fuse closed")
        # 16 accepted V8 tasks plus the accepted 1000-row pilot show at most
        # 1.350425 EECU-h per 1000 rows. Doubling this observed maximum is a
        # planning bound, not a guarantee of future GEE charges.
        observed_max_eecu_per_1000 = 1.350425
        estimated_remaining_eecu_h_2x = (sum(r["n_rows"] for r in planned)
                                          / 1000 * observed_max_eecu_per_1000 * 2)
        if budget["project_eecu_h"] + estimated_remaining_eecu_h_2x > budget_eecu:
            raise RuntimeError("Conservative 2x observed-max forecast exceeds budget fuse")
        wkt = core.read_json(core.root_files(ROOT)["v4"] / "config" / "recovery.json")["crs_wkt"]
        remote_names = {x.get("description") for x in remote}
        submitted = []
        log = HERE / "one_time_submission.jsonl"
        for row in planned:
            if row["name"] in remote_names:
                raise RuntimeError("Duplicate EE task name, stop: " + row["name"])
            members = data.loc[data.batch_id_v10.eq(row["key"])]
            if len(members) != row["n_rows"]:
                raise ValueError("Frozen weather batch membership changed")
            product = build_weather_1000(ee, members, wkt)
            task = ee.batch.Export.table.toDrive(
                collection=product, description=row["name"], folder=core.RUN,
                fileNamePrefix=row["name"], fileFormat="CSV", selectors=core.FIELDS)
            transition(conn, row["key"], "SUBMISSION_INTENT")
            task.start()
            transition(conn, row["key"], "READY", task_id=task.id,
                       operation=f"projects/{core.PROJECT}/operations/{task.id}")
            submitted.append({"key": row["key"], "task_id": task.id})
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"utc": now(), "key": row["key"],
                                    "task_id": task.id, "state": "SUBMITTED_NOT_QC"}) + "\n")
                f.flush()
                os.fsync(f.fileno())
            remote_names.add(row["name"])
            if len(submitted) % 25 == 0:
                print(json.dumps({"submitted_in_this_call": len(submitted),
                                  "remaining": len(planned) - len(submitted)}), flush=True)
        result = {
            "status": "ALL_PLANNED_WEATHER_GEE_TASKS_SUBMITTED_NOT_SCIENTIFICALLY_ACCEPTED",
            "submitted_now": len(submitted), "previously_not_planned": len(tasks) - len(planned),
            "total_tasks_in_v10": len(tasks),
            "project_month_conservative_eecu_h_at_submission": budget["project_eecu_h"],
            "remaining_forecast_eecu_h_2x_observed_max": estimated_remaining_eecu_h_2x,
            "queue_total_after_submission_upper_bound": active_remote + len(planned),
            "Drive_folder": core.RUN, "local_computer_required_after_submission": False,
            "scientific_QC_pending": True, "reconciliation": rec,
        }
        core.write_json(HERE / "one_time_submission_summary.json", result)
        return result


def audit_drive_available(max_batches: int = 50) -> dict:
    """One-time batch ingest from Drive; it never submits a GEE task.

    It can be run after the computer has been off while the queued GEE tasks
    finished. Each batch reads up to 10 CSVs directly from Drive into memory
    and writes one fingerprinted Parquet with scientific QC and source hashes.
    """
    if not 1 <= max_batches <= 100:
        raise ValueError("QC batch limit out of range")
    data, _ = validate_inputs()
    init()
    ee = eeops.initialize()
    remote = ee.data.getTaskList()
    accepted = 0
    batches = 0
    with database() as conn:
        rec = reconcile(conn, ee, remote)
        while batches < max_batches:
            pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE state='GEE_SUCCEEDED'").fetchone()[0]
            if pending == 0:
                break
            result = audit_successes(conn, data, force=True)
            if result.get("newly_accepted", 0) == 0:
                break
            accepted += result["newly_accepted"]
            batches += 1
        states = dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state").fetchall())
    return {"status": "DRIVE_BATCH_QC_FINISHED_NOT_NECESSARILY_GLOBAL_COMPLETE",
            "newly_accepted_tasks": accepted, "parquet_batches_written": batches,
            "task_states": states, "reconciliation": rec, "no_new_GEE_submission": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "status", "tick", "run", "submit-all", "audit-drive"])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-active", type=int, default=2)
    parser.add_argument("--budget-eecu", type=float, default=900)
    parser.add_argument("--max-qc-batches", type=int, default=50)
    args = parser.parse_args()
    if args.action == "init":
        print(json.dumps(init()))
    elif args.action == "status":
        print(json.dumps(tick(False), ensure_ascii=False))
    elif not args.execute:
        raise SystemExit("No GEE work starts without --execute")
    elif args.action == "tick":
        print(json.dumps(tick(True, args.max_active, args.budget_eecu), ensure_ascii=False))
    elif args.action == "submit-all":
        print(json.dumps(submit_all_once(args.budget_eecu), ensure_ascii=False))
    elif args.action == "audit-drive":
        print(json.dumps(audit_drive_available(args.max_qc_batches), ensure_ascii=False))
    else:
        loop(args.max_active, args.budget_eecu)
