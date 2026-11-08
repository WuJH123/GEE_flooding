"""Summarize actual accepted outputs, separate batch costs and project Monitoring."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from merit_direct_raster_pilot import HERE
from merit_hybrid_runner import DB
from merit_highlat_split_v10 import OUT


def read(name):
    return json.loads((HERE / name).read_text())


def main():
    merit = read("merit_independent_post_assembly_qc.json")
    weather = read("weather_independent_post_assembly_qc.json")
    budget = read("v10_budget_interpretation.json")
    if merit["status"] != "INDEPENDENT_GLOBAL_MERIT_QC_PASS" or \
       weather["status"] != "INDEPENDENT_POST_ASSEMBLY_QC_PASS":
        raise ValueError("Final products have not passed independent QC")
    with sqlite3.connect(DB) as conn:
        merit_jobs = conn.execute("SELECT state,COUNT(1),SUM(eecu_h) FROM jobs GROUP BY state").fetchall()
    with sqlite3.connect(HERE / "weather_v10.sqlite") as conn:
        weather_jobs = conn.execute("SELECT state,COUNT(1),SUM(eecu_h) FROM jobs GROUP BY state").fetchall()
    merit_jobs = {state: {"tasks": n, "recorded_eecu_h": cost} for state, n, cost in merit_jobs}
    weather_jobs = {state: {"tasks": n, "recorded_eecu_h": cost} for state, n, cost in weather_jobs}
    plan = pd.read_csv(OUT / "plan.csv")
    split_audits = [json.loads((OUT / key / "audit.json").read_text())
                    for key in plan.loc[~plan.pilot_reuse.astype(bool), "split_key"]]
    if len(split_audits) != 171 or any(a.get("status") != "QC_PASS" for a in split_audits):
        raise ValueError("A split task has not passed QC")
    if any(a.get("actual_eecu_h") is None for a in split_audits):
        raise ValueError("A split task lacks actual EECU")
    split_eecu = sum(float(a["actual_eecu_h"]) for a in split_audits)
    pilots = {site: read(f"merit_direct_pilots/{site}/audit.json")
              for site in ("wuhan", "coast")}
    old_split = read("merit_split_highlat_probe/audit.json")
    pilot_eecu = sum(float(a["actual_eecu_h"]) for a in pilots.values()) + float(old_split["actual_eecu_h"])
    if merit_jobs.get("QC_PASS", {}).get("tasks") != 1093 or \
       weather_jobs.get("ACCEPTED", {}).get("tasks") != 378:
        raise ValueError("Accepted GEE task count differs from frozen production")
    report = {
        "status": "GLOBAL_MERIT_AND_EVENT_WEATHER_SCIENTIFIC_QC_PASS",
        "project": "future-shuttle-513705-g9",
        "merit": {
            "frozen_GF10": merit["frozen_GF10"],
            "coverage_fraction": 1.0,
            "bands": merit["metric_bands_in_frozen_order"],
            "source_gap_rows": merit["source_gap_rows"],
            "source_gap_fraction": merit["source_gap_rows"] / merit["frozen_GF10"],
            "slope_missing_rows": merit["missing_per_band"]["merit_slope_mean_deg"],
            "output_sha256": merit["output_sha256"],
            "original_batch_jobs": merit_jobs,
            "accepted_highlat_split_tasks": 171,
            "reused_highlat_pilot_GF10": 386,
            "independent_seam_GF10": 450,
            "accepted_original_batch_eecu_h": merit_jobs["QC_PASS"]["recorded_eecu_h"],
            "accepted_highlat_split_eecu_h": split_eecu,
            "accepted_pilots_eecu_h": pilot_eecu,
            "accepted_batch_eecu_h_excluding_seam_API_calls":
                merit_jobs["QC_PASS"]["recorded_eecu_h"] + split_eecu + pilot_eecu,
            "failed_or_cancelled_original_tasks_without_recorded_eecu":
                merit_jobs.get("FAILED", {}).get("tasks", 0) +
                merit_jobs.get("CANCELLED", {}).get("tasks", 0),
        },
        "event_weather": {
            "GF10_UTC_rows": weather["rows"],
            "unique_GF10": weather["unique_GF10"],
            "IMERG_complete_window_counts": weather["complete_IMERG_window_counts"],
            "ERA5_soil_l1_missing_rows": weather["ERA5_soil_l1_missing_rows"],
            "ERA5_soil_l1_missing_fraction": weather["ERA5_soil_l1_missing_rows"] / weather["rows"],
            "output_sha256": weather["product_sha256"],
            "V10_jobs": weather_jobs,
            "V10_accepted_batch_eecu_h": weather_jobs["ACCEPTED"]["recorded_eecu_h"],
            "earlier_V7_V8_accepted_rows_reused": True,
            "reported_cases_and_unlabeled_calendar_candidates_not_true_flood_negatives": True,
        },
        "project_monthly_monitoring": {
            "asof_utc": budget["asof_utc"],
            "non_double_counting_usage_indicator_eecu_h":
                budget["non_double_counting_usage_indicator_eecu_h"],
            "monthly_user_allowance_eecu_h": budget["monthly_user_allowance_eecu_h"],
            "monitoring_can_lag": True,
            "not_equal_to_sum_of_these_two_accepted_products": True,
        },
    }
    target = HERE / "final_global_production_report_v10.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
