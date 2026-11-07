"""Download and audit every submitted split task, stopping on real failures."""
from __future__ import annotations

import json
import time

import pandas as pd

from merit_highlat_split_v10 import OUT, batch_audit


def main():
    plan = pd.read_csv(OUT / "plan.csv")
    expected = plan.loc[~plan.pilot_reuse.astype(bool)]
    log_path = OUT / "audit_loop.jsonl"
    while True:
        intents = sum((OUT / key / "intent.json").is_file() for key in expected.split_key)
        if intents != len(expected):
            raise RuntimeError(f"Only {intents}/{len(expected)} recovery tasks submitted")
        accepted_before = sum((OUT / key / "audit.json").is_file() and
                              json.loads((OUT / key / "audit.json").read_text()).get("status") == "QC_PASS"
                              for key in expected.split_key)
        if accepted_before == len(expected):
            print(json.dumps({"status": "ALL_SUBMITTED_SPLITS_QC_PASS",
                              "accepted_tasks": accepted_before}), flush=True)
            return
        result = batch_audit(50)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"accepted_before": accepted_before,
                                "QC_PASS_this_batch": result["QC_PASS"],
                                "GEE_FAILED_this_batch": result["GEE_FAILED"]}) + "\n")
        print(json.dumps({"accepted_before": accepted_before,
                          "QC_PASS_this_batch": result["QC_PASS"],
                          "GEE_FAILED_this_batch": result["GEE_FAILED"]}), flush=True)
        if result["GEE_FAILED"] or any(x.get("status") == "QC_FAIL" for x in result["audited"]):
            raise RuntimeError("Split GEE/QC failure: submission and assembly halt")
        time.sleep(30 if result["QC_PASS"] == 0 else 2)


if __name__ == "__main__":
    main()
