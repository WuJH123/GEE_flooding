"""Partition frozen GF10 once for source-native MERIT production.

Only wholly direct-safe 60x60 parent buckets use raster aggregation. Buckets
mixing >50,000-source-pixel cells use native weighted zonal statistics. The
three already-submitted direct pilots own their original cells, so no global
task can duplicate those accepted or pending results.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from merit_direct_raster_pilot import HERE, ROOT, SITES, SIZE

GRID = ROOT / "gee_ceegf10_v1/gf10_global_nonantarctic_land.parquet"
QUARANTINE = ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/plans/merit_quarantine_v4.csv"
CANDIDATE = HERE / "merit_direct60_candidate_tasks.csv"
MEMBERS = HERE / "merit_hybrid_members_v10.parquet"
TASKS = HERE / "merit_hybrid_tasks_v10.csv"
REPORT = HERE / "merit_hybrid_partition_qc.json"
GRID_SHA = "4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(4 << 20), b""):
            digest.update(piece)
    return digest.hexdigest()


def partition(grid: pd.DataFrame, quarantine: pd.DataFrame,
              candidate: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if len(grid) != 1395471 or grid.grid_id.duplicated().any():
        raise ValueError("Frozen GF10 identity/count mismatch")
    grid = grid[["grid_id", "grid_x", "grid_y"]].copy()
    grid.grid_x = grid.grid_x.astype(int)
    grid.grid_y = grid.grid_y.astype(int)
    if not (grid.grid_id == grid.grid_x.astype(str) + "_" + grid.grid_y.astype(str)).all():
        raise ValueError("GF10 ID/coordinate mismatch")
    grid["parent"] = ("merit_" + (grid.grid_x // 10 * 10).astype(str) + "_" +
                      (grid.grid_y // 10 * 10).astype(str) + "_10")
    if len(quarantine) != 14 or quarantine.tile_key.duplicated().any():
        raise ValueError("Quarantine plan is not the frozen 14 parents")
    grid["method"] = ""
    grid["task_key"] = ""
    seam = grid.parent.isin(set(quarantine.tile_key))
    if int(seam.sum()) != 450 or int(quarantine.n_land_cells.sum()) != 450:
        raise ValueError("Frozen 450 seam cells not conserved")
    grid.loc[seam, ["method", "task_key"]] = ["QUARANTINED_SEAM", "SEAM"]
    safe = grid.loc[~seam].copy()
    safe["bx"] = safe.grid_x // SIZE
    safe["by"] = safe.grid_y // SIZE
    if len(safe) != 1395021 or len(candidate) != 744 or int(candidate.n_GF10.sum()) != 1379686:
        raise ValueError("Safe/direct candidate counts changed")
    if candidate.duplicated(["bx", "by"]).any():
        raise ValueError("Duplicate direct parent bucket")
    candidate_index = candidate.set_index(["bx", "by"])
    actual_counts = safe.groupby(["bx", "by"]).size()
    if not set(candidate_index.index).issubset(set(actual_counts.index)):
        raise ValueError("Direct candidate references absent bucket")
    if (candidate_index.n_GF10 > actual_counts.loc[candidate_index.index]).any():
        raise ValueError("Direct candidate exceeds frozen safe GF10")

    # Preserve the immutable pilot members, regardless of whether the third
    # pilot has completed QC. A failed pilot must be explicitly reconciled.
    pilot_cells: set[str] = set()
    pilot_buckets: set[tuple[int, int]] = set()
    pilot_states: dict[str, str] = {}
    for site, (x, y) in SITES.items():
        pilot_path = HERE / "merit_direct_pilots" / site / "input_GF10.parquet"
        intent_path = pilot_path.parent / "intent.json"
        if not pilot_path.is_file() or not intent_path.is_file():
            raise ValueError(f"Missing immutable submitted pilot: {site}")
        pilot = pd.read_parquet(pilot_path)
        intent = json.loads(intent_path.read_text())
        if sha(pilot_path) != intent["input_SHA256"]:
            raise ValueError(f"Pilot member fingerprint changed: {site}")
        ids = set(pilot.grid_id.astype(str))
        actual = set(grid.loc[grid.grid_x.between(x, x + SIZE - 1) &
                              grid.grid_y.between(y, y + SIZE - 1), "grid_id"])
        if ids != actual or ids & pilot_cells or ids & set(grid.loc[seam, "grid_id"]):
            raise ValueError(f"Pilot/source overlap or seam violation: {site}")
        audit_path = pilot_path.parent / "audit.json"
        audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
        pilot_states[site] = audit.get("status", "UNAUDITED")
        if audit.get("status") == "SCIENTIFIC_QC_PASS_DIRECT_RASTER_PILOT":
            pilot_cells |= ids
            mask = safe.grid_id.isin(ids)
            safe.loc[mask, ["method", "task_key"]] = ["PILOT_DIRECT", "PILOT_" + site.upper()]
        elif audit.get("GEE_state") not in ("FAILED", "CANCELLED"):
            raise ValueError(f"Pilot has unresolved cloud/QC state: {site}")
        pilot_buckets |= set(zip((pilot.grid_x // SIZE).astype(int),
                                 (pilot.grid_y // SIZE).astype(int)))

    task_rows = []
    whole_direct = {
        key for key, row in candidate_index.iterrows()
        if (key not in pilot_buckets and -25 <= key[0] <= 25 and
            int(row.n_GF10) == int(actual_counts[key]))
    }
    for (bx, by), group in safe.groupby(["bx", "by"], sort=True):
        pending = group.loc[group.method.eq("")]
        if pending.empty:
            continue
        if (bx, by) in whole_direct:
            row = candidate_index.loc[(bx, by)]
            if len(pending) != int(row.n_GF10) or row.source_bbox_max > 50000:
                raise ValueError("Direct bucket source risk/identity mismatch")
            if (pending.grid_x.min() != int(row.x0) or
                pending.grid_x.max() != int(row.x1) or
                pending.grid_y.min() != int(row.y0) or
                pending.grid_y.max() != int(row.y1)):
                raise ValueError("Direct rectangle does not enclose exact members")
            key = f"MD10_{bx}_{by}"
            safe.loc[pending.index, ["method", "task_key"]] = ["DIRECT_RASTER", key]
            task_rows.append({"task_key": key, "method": "DIRECT_RASTER",
                              "x0": int(row.x0), "y0": int(row.y0),
                              "width": int(row.width), "height": int(row.height),
                              "n_GF10": len(pending), "source_bbox_max": int(row.source_bbox_max)})
        else:
            # Keep each native task small enough to stay within the already
            # verified 300-GF10 high-latitude export envelope.
            pending = pending.sort_values(["grid_y", "grid_x"])
            for index in range(0, len(pending), 300):
                chunk = pending.iloc[index:index + 300]
                key = f"MN10_{bx}_{by}_{index // 300:02d}"
                safe.loc[chunk.index, ["method", "task_key"]] = ["NATIVE_WEIGHTED", key]
                task_rows.append({"task_key": key, "method": "NATIVE_WEIGHTED",
                                  "x0": int(chunk.grid_x.min()),
                                  "y0": int(chunk.grid_y.min()),
                                  "width": int(chunk.grid_x.max() - chunk.grid_x.min() + 1),
                                  "height": int(chunk.grid_y.max() - chunk.grid_y.min() + 1),
                                  "n_GF10": len(chunk), "source_bbox_max": -1})
    if safe.method.eq("").any() or safe.task_key.eq("").any():
        raise ValueError("Unassigned frozen safe GF10")
    grid.loc[safe.index, ["method", "task_key"]] = safe[["method", "task_key"]]
    tasks = pd.DataFrame(task_rows)
    if tasks.task_key.duplicated().any():
        raise ValueError("Duplicate MERIT task keys")
    assigned = grid.loc[~seam]
    if int(tasks.n_GF10.sum()) + len(pilot_cells) != len(assigned):
        raise ValueError("Global MERIT partition conservation failed")
    report = {"status": "FROZEN_GF10_PARTITION_QC_PASS_NO_GLOBAL_SUBMISSION",
              "frozen_GF10": len(grid), "safe_GF10": len(safe),
              "seam_quarantine_GF10": int(seam.sum()),
              "pilot_submitted_GF10": len(pilot_cells),
              "direct_tasks": int(tasks.method.eq("DIRECT_RASTER").sum()),
              "direct_GF10": int(tasks.loc[tasks.method.eq("DIRECT_RASTER"), "n_GF10"].sum()),
              "native_tasks": int(tasks.method.eq("NATIVE_WEIGHTED").sum()),
              "native_GF10": int(tasks.loc[tasks.method.eq("NATIVE_WEIGHTED"), "n_GF10"].sum()),
              "total_new_tasks": len(tasks),
              "mixed_bucket_count": int(sum(0 < int(candidate_index.loc[key].n_GF10) < int(actual_counts[key])
                                            for key in candidate_index.index)),
              "pilot_buckets_excluded_from_new_direct": len(pilot_buckets),
              "pilot_states": pilot_states,
              "west_and_east_60km_buckets_native_due_to_real_westedge_failure": "abs(bx)>=26",
              "GF10_sha256": GRID_SHA}
    return grid[["grid_id", "grid_x", "grid_y", "method", "task_key"]], tasks, report


def main() -> None:
    if sha(GRID) != GRID_SHA:
        raise ValueError("Frozen GF10 SHA-256 mismatch")
    grid = pd.read_parquet(GRID, columns=["grid_id", "grid_x", "grid_y"])
    quarantine = pd.read_csv(QUARANTINE)
    candidate = pd.read_csv(CANDIDATE)
    members, tasks, report = partition(grid, quarantine, candidate)
    members.to_parquet(MEMBERS, index=False)
    tasks.to_csv(TASKS, index=False)
    report.update(members_sha256=sha(MEMBERS), tasks_sha256=sha(TASKS),
                  quarantine_plan_sha256=sha(QUARANTINE),
                  candidate_plan_sha256=sha(CANDIDATE))
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
