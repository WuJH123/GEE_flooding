"""Create global MERIT product only after every required result passes science QC."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time

import pandas as pd

from merit_direct_raster_pilot import HERE
from merit_hybrid_runner import DB
from merit_highlat_split_v10 import OUT


def status():
    with sqlite3.connect(DB) as conn:
        counts = dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state"))
    rows = pd.read_csv(OUT / "plan.csv")
    required = rows.loc[~rows.pilot_reuse.astype(bool)]
    accepted = 0
    for key in required.split_key:
        path = OUT / key / "audit.json"
        if not path.is_file():
            continue
        state = json.loads(path.read_text()).get("status")
        if state == "QC_FAIL":
            raise RuntimeError("High-lat science QC failed: " + key)
        if state == "QC_PASS":
            accepted += 1
    if counts.get("QC_FAIL", 0):
        raise RuntimeError("Original MERIT science QC failed")
    return {"original_QC_PASS": counts.get("QC_PASS", 0),
            "original_GEE_SUCCEEDED_not_audited": counts.get("GEE_SUCCEEDED", 0),
            "split_QC_PASS": accepted, "split_required": len(required)}


def main():
    while True:
        current = status()
        if current["original_QC_PASS"] == 1093 and current["split_QC_PASS"] == current["split_required"]:
            break
        time.sleep(60)
    for script in ("assemble_merit_hybrid_v10.py", "assemble_merit_global_v10.py"):
        subprocess.run([sys.executable, str(HERE / script)], check=True, cwd=HERE)
    report = json.loads((HERE / "merit_global_assembly_report.json").read_text())
    if report["status"] != "GLOBAL_1395471_GF10_QC_PASS" or report["QC_accepted_GF10"] != 1395471:
        raise RuntimeError("Final MERIT global GF10 coverage failed")
    print(json.dumps({"status": "GLOBAL_MERIT_FINALIZED_QC_PASS",
                      "output": report["output"],
                      "sha256": report["output_sha256"]}), flush=True)


if __name__ == "__main__":
    main()
