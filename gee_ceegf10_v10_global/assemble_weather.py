"""Assemble only scientifically accepted GF10×UTC exposure rows.

This is a resumable local consolidation of GEE Drive CSV QC products.  The
output stays explicitly PARTIAL until it covers the frozen source universe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(r"E:\GEE_flooding")
HERE = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
V8 = ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"
sys.path.insert(0, str(V8))
from cee_v8 import core  # noqa: E402
from weather_runner import _check_weather_frame, validate_inputs  # noqa: E402


def pairs(frame: pd.DataFrame) -> set[tuple[str, str]]:
    return set(zip(frame.grid_id.astype(str), frame.date_utc.astype(str)))


def main() -> dict:
    expected_v10, plan = validate_inputs()
    source = pd.read_parquet(V8 / "plans" / "weather_grid_days.parquet")
    v7 = pd.read_parquet(V8 / "plans" / "accepted_v7_weather.parquet")
    universe = pairs(source) | pairs(v7)
    if len(universe) != 275152 or len(source) != 275106 or len(v7) != 46:
        raise ValueError("Frozen GF10×UTC source universe changed")
    frames = [v7.loc[:, core.FIELDS].assign(source_batch="V7_ACCEPTED")]
    manifest = [{"source": "V7", "n_rows": len(v7),
                 "sha256": core.sha(V8 / "plans" / "accepted_v7_weather.parquet")}]

    with sqlite3.connect(V8 / "reports" / "v8_production.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        old = conn.execute("SELECT * FROM jobs WHERE family='weather' AND state='ACCEPTED'").fetchall()
    for row in old:
        path = V8 / "downloads" / row["file_name"]
        if not path.exists() or core.sha(path) != row["local_sha"]:
            raise ValueError("V8 accepted CSV fingerprint mismatch: " + row["key"])
        frame = pd.read_csv(path, dtype={"grid_id": "string", "date_utc": "string"})
        if len(frame) != row["n_rows"]:
            raise ValueError("V8 accepted CSV row count mismatch: " + row["key"])
        frames.append(frame.loc[:, core.FIELDS].assign(source_batch=row["key"]))
        manifest.append({"source": row["key"], "n_rows": len(frame), "sha256": row["local_sha"]})

    pilot_dir = V8 / "reports" / "weather_1000_live_canary"
    pilot_report = json.loads((pilot_dir / "audit.json").read_text(encoding="utf-8"))
    if pilot_report["status"] != "SCIENTIFIC_QC_PASS":
        raise ValueError("Weather 1000 pilot no longer scientifically accepted")
    pilot_file = pilot_dir / "CEE_GF10_GLOBAL_EE_V8_20261106_W1000_2021SEP01_03_04.csv"
    if core.sha(pilot_file) != pilot_report["csv_sha256"]:
        raise ValueError("Pilot CSV fingerprint mismatch")
    pilot = pd.read_csv(pilot_file, dtype={"grid_id": "string", "date_utc": "string"})
    pilot = pilot.loc[~pd.Series(list(zip(pilot.grid_id, pilot.date_utc)),
                                  index=pilot.index).isin(pairs(v7))]
    if len(pilot) != 975:
        raise ValueError("Pilot 975 source rows changed")
    frames.append(pilot.loc[:, core.FIELDS].assign(source_batch="W1000_ACCEPTED"))
    manifest.append({"source": "W1000", "n_rows": len(pilot),
                     "sha256": pilot_report["csv_sha256"]})

    with sqlite3.connect(HERE / "weather_v10.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        jobs = conn.execute("SELECT * FROM jobs WHERE state='ACCEPTED'").fetchall()
    accepted = {row["key"]: row for row in jobs}
    seen = set()
    for qc_path in sorted((HERE / "parquet_batches").glob("*.qc.json")):
        qc = json.loads(qc_path.read_text(encoding="utf-8"))
        path = qc_path.with_name(qc_path.name.removesuffix(".qc.json") + ".parquet")
        if qc["status"] != "BATCH_SCIENTIFIC_QC_PASS" or core.sha(path) != qc["parquet_sha256"]:
            raise ValueError("V10 QC Parquet fingerprint mismatch: " + str(path))
        frame = pd.read_parquet(path)
        keys = {item["key"] for item in qc["source_csv_and_EECU"]}
        if len(frame) != qc["n_rows"] or keys != set(frame.batch_id_v10):
            raise ValueError("V10 QC Parquet membership mismatch")
        if keys & seen or not keys <= accepted.keys():
            raise ValueError("Duplicate or unaccepted V10 batch")
        seen |= keys
        for item in qc["source_csv_and_EECU"]:
            if accepted[item["key"]]["local_sha"] != item["csv_sha256"]:
                raise ValueError("V10 accepted CSV hash differs from batch manifest")
        frames.append(frame.loc[:, core.FIELDS].assign(source_batch=frame.batch_id_v10))
        manifest.append({"source": path.name, "n_rows": len(frame),
                         "sha256": qc["parquet_sha256"], "n_tasks": len(keys)})

    for key, row in accepted.items():
        if key in seen:
            continue
        path = HERE / "downloads" / (row["name"] + ".csv")
        if not path.exists() or core.sha(path) != row["local_sha"]:
            raise ValueError("V10 per-file accepted CSV fingerprint mismatch: " + key)
        frame = pd.read_csv(path, dtype={"grid_id": "string", "date_utc": "string"})
        expected = expected_v10.loc[expected_v10.batch_id_v10.eq(key)]
        _check_weather_frame(frame, expected)
        frames.append(frame.loc[:, core.FIELDS].assign(source_batch=key))
        manifest.append({"source": key, "n_rows": len(frame), "sha256": row["local_sha"]})

    combined = pd.concat(frames, ignore_index=True)
    if len(combined) != len(pairs(combined)) or not pairs(combined) <= universe:
        raise ValueError("Duplicate or invented GF10×UTC exposure row")
    complete = len(combined) == len(universe)
    output = HERE / ("weather_exposure_GLOBAL_QC_PASS.parquet" if complete else
                     "weather_exposure_PARTIAL_QC_PASS.parquet")
    temporary = output.with_suffix(".parquet.part")
    combined.to_parquet(temporary, index=False)
    temporary.replace(output)
    report = {"status": "GLOBAL_SCIENTIFIC_QC_PASS" if complete else "PARTIAL_SCIENTIFIC_QC_PASS",
              "frozen_source_GF10_UTC_rows": len(universe), "accepted_rows": len(combined),
              "unaccepted_rows": len(universe) - len(combined),
              "coverage_fraction": len(combined) / len(universe),
              "ERA5_soil_l1_missing_rows": int(combined.era5_soil_l1_prevday_m3m3.isna().sum()),
              "IMERG_day_count_incomplete_rows": int(combined.imerg_n_obs_day.ne(48).sum()),
              "output": str(output), "output_sha256": core.sha(output),
              "source_manifest": manifest,
              "no_unaccepted_GEE_results_included": True,
              "news_absence_is_not_flood_absence": True}
    (HERE / "weather_assembly_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = main()
    print(json.dumps({key: value for key, value in result.items() if key != "source_manifest"}, indent=2))
