"""Submit audited high-lat recovery batches, with failure and budget gates."""
from __future__ import annotations

import json

import pandas as pd

from merit_highlat_split_v10 import OUT, batch_submit


def first_gate():
    rows = pd.read_csv(OUT / "plan.csv")
    first = rows.loc[~rows.pilot_reuse.astype(bool)].head(10)
    for row in first.itertuples(index=False):
        audit = json.loads((OUT / row.split_key / "audit.json").read_text())
        if audit.get("status") != "QC_PASS":
            raise RuntimeError("First 10 high-lat split tasks have not all passed QC")


def main():
    first_gate()
    log_path = OUT / "dispatch.jsonl"
    while True:
        result = batch_submit(25, True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        print(json.dumps({"submitted": len(result["submitted"]),
                          "remaining": result["remaining_after"]}), flush=True)
        if result["remaining_after"] == 0:
            break
        if not result["submitted"]:
            raise RuntimeError("Dispatch stopped without completing plan")


if __name__ == "__main__":
    main()
