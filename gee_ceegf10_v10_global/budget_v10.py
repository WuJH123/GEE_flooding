"""Interpret project-wide Monitoring EECU without double-counting a task.

The two Earth Engine CPU metrics are DELTA streams for the same requests:
in_progress reports usage while requests run; usage_time reports successful
requests when finished. Their monthly sums are not two disjoint expenses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ee

ROOT = Path(r"E:\GEE_flooding")
HERE = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import budget_v9, core  # noqa: E402


def read() -> dict:
    ee.Initialize(project=core.PROJECT)
    raw = budget_v9.current_month_eecu_hours(core.PROJECT)
    tasks = ee.data.getTaskList()
    running = [x for x in tasks if x.get("state") == "RUNNING"]
    running_reported = sum(float(x.get("batch_eecu_usage_seconds", 0) or 0) / 3600
                           for x in running)
    completed = raw["completed_eecu_h"]
    progress = raw["inprogress_eecu_h"]
    result = {
        "status": "MONITORING_METRICS_INTERPRETED_NO_DOUBLE_COUNT_CLAIM",
        "project": core.PROJECT, "asof_utc": raw["asof_utc"],
        "completed_successful_requests_eecu_h": completed,
        "inprogress_metric_month_sum_eecu_h_overlaps_completed": progress,
        "running_tasks": len(running),
        "running_operation_reported_eecu_h": running_reported,
        "non_double_counting_usage_indicator_eecu_h": max(completed + running_reported, progress),
        "strict_double_count_upper_bound_eecu_h": completed + progress,
        "monthly_user_allowance_eecu_h": 1000,
        "new_merit_submission_pause_eecu_h": 900,
        "monitoring_can_lag": True,
        "metric_interpretation": "in_progress DELTA is reported during requests; successful request usage_time DELTA is reported at completion; adding monthly totals counts successful work twice",
        "source": "https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h#earthengine",
    }
    (HERE / "v10_budget_interpretation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(read(), indent=2))
