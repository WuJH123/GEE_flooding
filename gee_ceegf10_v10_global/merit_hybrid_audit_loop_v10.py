"""Resume Drive download/science QC until all completed MERIT jobs are audited.

This is local postprocessing only; it does not submit or repeat GEE tasks.
"""
from __future__ import annotations

import json
import sqlite3
import time

from merit_hybrid_runner import DB, audit
from merit_direct_raster_pilot import HERE

LOG = HERE / "merit_hybrid_qc_loop.jsonl"


def counts():
    with sqlite3.connect(DB) as conn:
        return dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state"))


def main():
    while True:
        before = counts()
        if before.get("GEE_SUCCEEDED", 0) == 0:
            break
        result = audit(100)
        after = counts()
        record = {"before": before, "after": after,
                  "batch_QC_PASS": sum(r["state"] == "QC_PASS" for r in result["results"]),
                  "batch_QC_FAIL": sum(r["state"] == "QC_FAIL" for r in result["results"]),
                  "batch_DRIVE_PENDING": sum(r["state"] == "GEE_SUCCEEDED_DRIVE_PENDING"
                                             for r in result["results"])}
        with LOG.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
        if record["batch_QC_FAIL"]:
            raise RuntimeError("Scientific QC failure; see per-task audit and loop log")
        if after.get("GEE_SUCCEEDED", 0) >= before.get("GEE_SUCCEEDED", 0):
            # Drive listing may lag. Do not spin or count a pending file as accepted.
            break
        time.sleep(2)
    return counts()


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
