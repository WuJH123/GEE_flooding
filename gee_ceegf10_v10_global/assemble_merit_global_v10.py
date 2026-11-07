"""Unite QC-accepted safe MERIT and independently audited seam 450 GF10."""
import json
import sys
from pathlib import Path

import pandas as pd

from merit_direct_raster_pilot import HERE, ROOT

sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core  # noqa: E402


def main() -> dict:
    grid_path = ROOT / "gee_ceegf10_v1/gf10_global_nonantarctic_land.parquet"
    if core.sha(grid_path) != core.GRID_SHA:
        raise ValueError("Frozen GF10 source changed")
    safe_report = json.loads((HERE / "merit_hydro_assembly_report.json").read_text())
    seam_report = json.loads((HERE / "merit_seam450_audit.json").read_text())
    if safe_report["status"] not in ("PARTIAL_SAFE_QC_PASS", "ALL_SAFE_QC_PASS_SEAM_450_QUARANTINED"):
        raise ValueError("Safe MERIT assembly not scientifically audited")
    if seam_report["status"] != "SEAM450_SOURCE_PIXEL_QC_PASS_FOR_GLOBAL_ASSEMBLY":
        raise ValueError("Seam 450 independent source QC not passed")
    safe_path, seam_path = Path(safe_report["output"]), Path(seam_report["output"])
    if core.sha(safe_path) != safe_report["output_sha256"] or core.sha(seam_path) != seam_report["output_sha256"]:
        raise ValueError("QC source Parquet SHA-256 changed")
    safe = pd.read_parquet(safe_path)
    seam = pd.read_parquet(seam_path)
    if len(safe) != safe_report["accepted_GF10"] or len(seam) != 450:
        raise ValueError("Safe/seam output row count changed")
    if list(safe.columns) != list(seam.columns):
        raise ValueError("MERIT 16-metric schema differs across safe/seam source methods")
    result = pd.concat([safe,seam],ignore_index=True)
    if result.grid_id.duplicated().any():
        raise ValueError("Duplicate GF10 in global MERIT candidate")
    grid = pd.read_parquet(grid_path,columns=["grid_id"])
    if not set(result.grid_id).issubset(set(grid.grid_id)):
        raise ValueError("Global MERIT source contains invented GF10")
    complete = len(result) == core.GRID_ROWS and set(result.grid_id) == set(grid.grid_id)
    status = "GLOBAL_1395471_GF10_QC_PASS" if complete else "GLOBAL_PARTIAL_QC_PASS_CLOUD_TASKS_PENDING"
    output = HERE / ("merit_hydro_GLOBAL_QC_PASS.parquet" if complete else
                     "merit_hydro_GLOBAL_PARTIAL_QC_PASS.parquet")
    result.to_parquet(output,index=False)
    report = {"status": status, "frozen_GF10": core.GRID_ROWS,
              "QC_accepted_GF10": len(result),
              "coverage_fraction": len(result)/core.GRID_ROWS,
              "safe_QC_accepted_GF10": len(safe),
              "seam_source_QC_accepted_GF10": len(seam),
              "source_gap_rows": int(result.merit_valid_fraction.fillna(0).eq(0).sum()),
              "missing_per_band": {band:int(result[band].isna().sum()) for band in core.BANDS},
              "source_safe_sha256": safe_report["output_sha256"],
              "source_seam_sha256": seam_report["output_sha256"],
              "source_methods_separately_recorded": True,
              "no_unaccepted_tasks_included": True,
              "output": str(output), "output_sha256": core.sha(output)}
    (HERE / "merit_global_assembly_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(),indent=2))
