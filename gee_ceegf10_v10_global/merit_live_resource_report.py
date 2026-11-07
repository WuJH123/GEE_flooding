"""Read-only cloud status, billed EECU and current scientific coverage."""
import json
import sqlite3
import statistics

import ee

from merit_direct_raster_pilot import HERE
from merit_hybrid_runner import DB
from plan_merit_hybrid_v10 import REPORT

ee.Initialize(project="future-shuttle-513705-g9")
prefix = "CEE_GF10_MERIT_HYBRID_V10_"
remote = [x for x in ee.data.getTaskList() if str(x.get("description", "")).startswith(prefix)]
ledger = sqlite3.connect(DB).execute("SELECT task_key,task_id,state FROM jobs").fetchall()
by_key = {x["description"][len(prefix):]: x for x in remote}
if len(remote) != len(by_key) or len(ledger) != len(remote):
    raise ValueError("GEE remote/global ledger task count or names do not match")
for key, task_id, _ in ledger:
    if key not in by_key or by_key[key].get("id") != task_id:
        raise ValueError("Remote task ID mismatch: " + key)
completed = [x for x in remote if x.get("state") == "COMPLETED"]
runtime = [(x["update_timestamp_ms"] - x["start_timestamp_ms"]) / 1000
           for x in completed if x.get("update_timestamp_ms") and x.get("start_timestamp_ms")]
wait = [(x["start_timestamp_ms"] - x["creation_timestamp_ms"]) / 1000
        for x in completed if x.get("start_timestamp_ms") and x.get("creation_timestamp_ms")]
states = {state: sum(x.get("state") == state for x in remote)
          for state in ("READY", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")}
assembly = json.loads((HERE / "merit_hydro_assembly_report.json").read_text())
partition = json.loads(REPORT.read_text())
result = {"status": "LIVE_GEE_OPERATION_AND_LOCAL_QC_SEPARATED",
          "remote_task_count": len(remote), "remote_states": states,
          "remote_task_ids_match_sqlite": True,
          "completed_operation_eecu_h": sum(float(x.get("batch_eecu_usage_seconds") or 0) / 3600
                                            for x in completed),
          "completed_operation_runtime_seconds_median": statistics.median(runtime) if runtime else None,
          "completed_operation_runtime_seconds_max": max(runtime) if runtime else None,
          "completed_operation_wait_seconds_median": statistics.median(wait) if wait else None,
          "failed_tasks": [{"key": x["description"][len(prefix):],
                            "error": x.get("error_message"), "task_id": x.get("id")}
                           for x in remote if x.get("state") in ("FAILED", "CANCELLED")],
          "safe_GF10": partition["safe_GF10"],
          "QC_accepted_GF10": assembly["accepted_GF10"],
          "QC_safe_coverage_fraction": assembly["safe_coverage_fraction"],
          "seam_quarantine_GF10": 450,
          "GEE_completed_is_not_QC_completed": True}
(HERE / "merit_live_resource_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
