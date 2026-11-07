"""Read-only scientific gate for the two source-native MERIT exports.

No global task may be submitted merely because this script finds a CSV.  The
native estimator differs from the historical 500 m two-pass estimator, so its
independent source-pixel diagnostics and source-gap rate are reported openly.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(r"E:\GEE_flooding")
HERE = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, download  # noqa: E402
from native_merit_pilot import MEAN_NAMES, SELECTORS, output_paths, sha  # noqa: E402

RENAME = {
    "hnd_p10": "merit_hand_p10_m",
    "hnd_p50": "merit_hand_p50_m",
    "hnd_p90": "merit_hand_p90_m",
    "upa_max": "merit_upa_max_km2",
    "upa_p90": "merit_upa_p90_km2",
}
PCT = ["merit_hand_p10_m", "merit_hand_p50_m", "merit_hand_p90_m"]
REFERENCE = {"wuhan": "1080_350", "greenland": "-500_723",
             "wuhan_join": "1080_350", "greenland_join": "-500_723",
             "westedge_join": "-1720_679",
             "wuhan_weighted": "1080_350", "greenland_weighted": "-500_723",
             "westedge_weighted": "-1720_679"}


def check_frame(frame: pd.DataFrame, expected: pd.DataFrame) -> dict:
    if not set(SELECTORS) <= set(frame):
        raise ValueError("Missing native MERIT output columns: " +
                         ",".join(sorted(set(SELECTORS) - set(frame))))
    frame["grid_id"] = frame.grid_id.astype(str)
    ids = expected.grid_id.astype(str)
    if len(frame) != len(expected) or frame.grid_id.duplicated().any() or set(frame.grid_id) != set(ids):
        raise ValueError("GF10 output member mismatch or duplicate")
    for band in SELECTORS[1:]:
        frame[band] = pd.to_numeric(frame[band], errors="coerce")
    finite = frame[SELECTORS[1:]].apply(lambda c: c.map(lambda x: pd.isna(x) or math.isfinite(x))).all(axis=1)
    if not bool(finite.all()):
        raise ValueError("Infinite native MERIT statistic")
    for band in ("merit_permanent_water_fraction", "merit_valid_fraction",
                 "merit_hand_le2_fraction_valid", "merit_hand_le5_fraction_valid",
                 "merit_hand_le10_fraction_valid", "merit_slope_le2_fraction_valid"):
        if not bool(frame[band].dropna().between(-1e-5, 1.00001).all()):
            raise ValueError("Fraction outside [0,1]: " + band)
    def ordered_if_observed(left, right, tolerance=0.0):
        observed = left.notna() & right.notna()
        return bool((left[observed] <= right[observed] + tolerance).all())
    if not (ordered_if_observed(frame.merit_hand_le2_fraction_valid,
                                frame.merit_hand_le5_fraction_valid, 1e-5) and
            ordered_if_observed(frame.merit_hand_le5_fraction_valid,
                                frame.merit_hand_le10_fraction_valid, 1e-5)):
        raise ValueError("HAND low-elevation threshold fractions not nested")
    valid = frame.merit_valid_fraction.fillna(0).gt(0)
    if not bool(frame.loc[valid, ["merit_hand_mean_m", "hnd_p10", "hnd_p50", "hnd_p90"]].notna().all().all()):
        raise ValueError("Missing HAND metric despite source coverage")
    if not (ordered_if_observed(frame.hnd_p10, frame.hnd_p50) and
            ordered_if_observed(frame.hnd_p50, frame.hnd_p90)):
        raise ValueError("HAND quantile ordering invalid")
    if not ordered_if_observed(frame.upa_p90, frame.upa_max, 1e-4):
        raise ValueError("UPA p90 exceeds UPA maximum")
    if not bool(frame.merit_slope_mean_deg.dropna().between(0, 90.0001).all()):
        raise ValueError("Slope outside degrees range")
    if not bool(frame.upa_max.dropna().ge(0).all()):
        raise ValueError("Negative UPA maximum")
    if not bool(frame.merit_upa_mean_km2.dropna().ge(0).all()):
        raise ValueError("Negative UPA mean")
    if not ordered_if_observed(frame.merit_upa_mean_km2, frame.upa_max, 1e-4):
        raise ValueError("UPA mean exceeds source-pixel maximum")
    return {"n_GF10": len(frame), "source_gap_count": int((~valid).sum()),
            "missing_per_band": {band: int(frame[band].isna().sum()) for band in SELECTORS[1:]}}


def source_pixel_comparison(frame: pd.DataFrame, grid_id: str) -> dict:
    path = HERE / f"raw_source_metrics_{grid_id}.json"
    if not path.exists():
        raise ValueError("Missing independent source-pixel report: " + grid_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw["grid_id"] != grid_id or raw["source"] != "MERIT/Hydro/v1_0_1":
        raise ValueError("Independent source-pixel provenance mismatch")
    actual = frame.set_index("grid_id").loc[grid_id]
    reverse = {value: key for key, value in RENAME.items()}
    diffs = {}
    for name, reference in raw["metrics"].items():
        if reference is None:
            continue
        col = reverse.get(name, name)
        estimate = float(actual[col])
        difference = estimate - float(reference)
        diffs[name] = {"GEE_native": estimate, "raw_source_area_weighted": float(reference),
                       "absolute_difference": abs(difference),
                       "relative_difference": abs(difference) / max(abs(float(reference)), 1.0)}
    failures = []
    for name, item in diffs.items():
        delta = item["absolute_difference"]
        reference = abs(item["raw_source_area_weighted"])
        if name.startswith("merit_hand_p"):
            tolerance = 0.11  # one 0.1 m source quantization increment
        elif name == "merit_upa_p90_km2":
            tolerance = max(0.001, 0.0001 * reference)
        elif "fraction" in name:
            tolerance = 0.001
        else:
            tolerance = max(0.002, 0.0001 * reference)
        item["science_tolerance"] = tolerance
        if delta > tolerance:
            failures.append(name)
    return {"grid_id": grid_id, "comparison": diffs,
            "n_raw_source_metrics_compared": len(diffs),
            "source_pixel_tolerance_pass": len(failures) == 0,
            "source_pixel_failures": failures,
            "slope_requires_separate_graph_QC": True,
            "independent_pixel_report_sha256": sha(path)}


def _drive_csv(name: str) -> tuple[bytes, str] | None:
    session = download._drive_session()
    response = session.get("https://www.googleapis.com/drive/v3/files", params={
        "q": f"name = '{name}.csv' and trashed = false",
        "fields": "nextPageToken,files(id,name,parents)", "pageSize": 100}, timeout=60)
    response.raise_for_status()
    listing = response.json()
    if listing.get("nextPageToken") or len(listing.get("files", [])) > 1:
        raise ValueError("Ambiguous Drive CSV name: " + name)
    if not listing.get("files"):
        return None
    item = listing["files"][0]
    response = session.get("https://www.googleapis.com/drive/v3/files/" + item["id"],
                           params={"alt": "media"}, timeout=180)
    response.raise_for_status()
    return response.content, item["id"]


def audit(site: str) -> dict:
    directory, input_path, intent_path, name = output_paths(site)
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if intent["name"] != name or intent["input_sha256"] != sha(input_path):
        raise ValueError("Immutable pilot intent or input changed")
    ee.Initialize(project=intent["project"])
    statuses = ee.data.getTaskStatus([intent["task_id"]])
    if len(statuses) != 1 or statuses[0].get("id") != intent["task_id"]:
        raise ValueError("Real GEE operation cannot be reconciled")
    status = statuses[0]
    report = {"site": site, "task_id": intent["task_id"], "GEE_state": status["state"],
              "source_input_sha256": intent["input_sha256"],
              "scientific_method": intent["science_method"],
              "historical_v7_values_not_interchangeable": True}
    if status["state"] != "COMPLETED":
        report["status"] = "PENDING_OR_GEE_FAILED_NOT_SCIENCE_ACCEPTED"
        report["GEE_error"] = status.get("error_message")
    else:
        operation = ee.data.getOperation(status["name"])
        seconds = (operation.get("metadata") or {}).get("batchEecuUsageSeconds")
        report["actual_EECU_h"] = float(seconds) / 3600 if seconds is not None else None
        if report["actual_EECU_h"] is None:
            report["status"] = "GEE_SUCCEEDED_EECU_REPORT_PENDING"
            result = None
        else:
            result = _drive_csv(name)
        if result is None and "status" not in report:
            report["status"] = "GEE_SUCCEEDED_DRIVE_FILE_PENDING"
        elif result is not None:
            raw, file_id = result
            frame = pd.read_csv(io.BytesIO(raw), dtype={"grid_id": "string"})
            expected = pd.read_parquet(input_path)
            report["quality"] = check_frame(frame, expected)
            report["independent_raw_check"] = source_pixel_comparison(frame, REFERENCE[site])
            report["drive_file_id"] = file_id
            report["drive_csv_sha256"] = hashlib.sha256(raw).hexdigest()
            if not report["independent_raw_check"]["source_pixel_tolerance_pass"]:
                report["status"] = "PILOT_SOURCE_PIXEL_SCIENCE_FAIL"
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                return report
            frame = frame.rename(columns=RENAME)
            frame["merit_upa_max_log1p"] = frame.merit_upa_max_km2.clip(lower=0).add(1).map(math.log)
            frame = frame.loc[:, ["grid_id"] + core.BANDS]
            output = directory / "native_science_candidate.parquet"
            if output.exists():
                previous = pd.read_parquet(output)
                if not previous.equals(frame):
                    raise ValueError("Existing native candidate Parquet differs from Drive source")
            else:
                frame.to_parquet(output, index=False)
            report["parquet_sha256"] = sha(output)
            report["status"] = "PILOT_QC_RECORDED_GLOBAL_METHOD_APPROVAL_PENDING"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=sorted(REFERENCE), required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.site), ensure_ascii=False, indent=2))
