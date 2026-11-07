"""Conservative pilot-grounded MERIT task and EECU planning report."""
import json
import sqlite3

import pandas as pd

from merit_direct_raster_pilot import HERE
from merit_hybrid_runner import DB, pilot_gate
from plan_merit_hybrid_v10 import TASKS, REPORT, sha

tasks = pd.read_csv(TASKS)
partition = json.loads(REPORT.read_text())
gate = pilot_gate()
direct_rate = max(gate["direct_pilot_eecu_h"].values()) / 3499
native_rate = max(gate["native_pilot_eecu_h"].values()) / 300
for method, rate in [("DIRECT_RASTER", direct_rate), ("NATIVE_WEIGHTED", native_rate)]:
    tasks.loc[tasks.method.eq(method), "pilot_rate_upper_eecu_per_GF10"] = rate
tasks["threefold_reserve_eecu_h"] = tasks.pilot_rate_upper_eecu_per_GF10 * tasks.n_GF10 * 3
weather = sqlite3.connect(HERE / "weather_v10.sqlite").execute(
    "SELECT COUNT(*),SUM(eecu_h) FROM jobs WHERE state='ACCEPTED'").fetchone()
merit = sqlite3.connect(DB).execute(
    "SELECT state,COUNT(*),COALESCE(SUM(eecu_h),0) FROM jobs GROUP BY state").fetchall()
budget = json.loads((HERE / "v10_budget_interpretation.json").read_text())
report = {"status": "PILOT_GROUNDED_BUDGET_FORECAST_NOT_ACTUAL_GLOBAL_COST",
          "source_task_plan_sha256": sha(TASKS),
          "frozen_GF10": partition["frozen_GF10"],
          "seam_quarantine_GF10": partition["seam_quarantine_GF10"],
          "new_merit_tasks": len(tasks),
          "new_merit_GF10": int(tasks.n_GF10.sum()),
          "direct_pilot_eecu_h": gate["direct_pilot_eecu_h"],
          "native_pilot_eecu_h": gate["native_pilot_eecu_h"],
          "threefold_merit_reserve_eecu_h": float(tasks.threefold_reserve_eecu_h.sum()),
          "threefold_reserve_by_method": tasks.groupby("method").threefold_reserve_eecu_h.sum().to_dict(),
          "weather_accepted_v10_tasks": weather[0],
          "weather_v10_actual_eecu_h": weather[1],
          "merit_task_states_actual": {row[0]: {"tasks": row[1], "reported_eecu_h": row[2]}
                                       for row in merit},
          "project_indicator_asof_utc": budget["asof_utc"],
          "project_non_double_counting_indicator_eecu_h":
              budget["non_double_counting_usage_indicator_eecu_h"],
          "project_indicator_plus_threefold_new_merit_reserve_eecu_h":
              budget["non_double_counting_usage_indicator_eecu_h"] +
              float(tasks.threefold_reserve_eecu_h.sum()),
          "submission_pause_eecu_h": 900,
          "uncertainty": "Three times the highest tested per-cell EECU is a budget guard, not a certified global upper bound; verify each cloud operation and pause on failures."}
(HERE / "merit_hybrid_cost_forecast.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
