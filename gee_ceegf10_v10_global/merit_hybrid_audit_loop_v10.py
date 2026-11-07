"""Resume Drive download/science QC until all completed MERIT jobs are audited.

This is local postprocessing only; it does not submit or repeat GEE tasks.
"""
from __future__ import annotations

import json
import argparse
import hashlib
import sqlite3
import time

from merit_hybrid_runner import DB, audit
from merit_direct_raster_pilot import HERE

LOG = HERE / "merit_hybrid_qc_loop.jsonl"


def counts(shard_index=None, shard_count=None):
    with sqlite3.connect(DB) as conn:
        if shard_index is None:
            return dict(conn.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state"))
        rows = conn.execute("SELECT task_key,state FROM jobs WHERE method='NATIVE_WEIGHTED'").fetchall()
    selected = [state for key, state in rows if
                int.from_bytes(hashlib.blake2s(key.encode(), digest_size=4).digest(), "big")
                % shard_count == shard_index]
    return {state: selected.count(state) for state in set(selected)}


def main(shard_index=None, shard_count=None):
    log = (HERE / f"merit_native_qc_shard_{shard_index}.jsonl" if shard_index is not None
           else LOG)
    while True:
        before = counts(shard_index, shard_count)
        if before.get("GEE_SUCCEEDED", 0) == 0:
            break
        result = audit(100, shard_index, shard_count)
        after = counts(shard_index, shard_count)
        record = {"before": before, "after": after,
                  "batch_QC_PASS": sum(r["state"] == "QC_PASS" for r in result["results"]),
                  "batch_QC_FAIL": sum(r["state"] == "QC_FAIL" for r in result["results"]),
                  "batch_DRIVE_PENDING": sum(r["state"] == "GEE_SUCCEEDED_DRIVE_PENDING"
                                             for r in result["results"])}
        with log.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
        if record["batch_QC_FAIL"]:
            raise RuntimeError("Scientific QC failure; see per-task audit and loop log")
        if after.get("GEE_SUCCEEDED", 0) >= before.get("GEE_SUCCEEDED", 0):
            # Drive listing may lag. Do not spin or count a pending file as accepted.
            break
        time.sleep(2)
    return counts(shard_index, shard_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-shard-index", type=int)
    parser.add_argument("--native-shard-count", type=int)
    args = parser.parse_args()
    if (args.native_shard_index is None) != (args.native_shard_count is None):
        parser.error("Provide both native shard index and count")
    print(json.dumps(main(args.native_shard_index, args.native_shard_count), indent=2))
