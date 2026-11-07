"""Accept the 450 seam GF10 only after exact-source 14-parent audit."""
import json
import math
from pathlib import Path

import pandas as pd

from seam_exact_parent_v10 import GRID, HERE, OUT, QUARANTINE

import sys
sys.path.insert(0, r"E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106")
from cee_v8 import core  # noqa: E402


def main() -> dict:
    if core.sha(GRID) != core.GRID_SHA:
        raise ValueError("Frozen GF10 hash changed")
    independent = json.loads((HERE / "seam_source_16_validation.json").read_text())
    if independent["status"] != "RAW_SOURCE_ALL_16_NON_SEAM_VALIDATION_PASS" or len(independent["references"]) < 3:
        raise ValueError("Source-native all-16 independent reference gate missing")
    if any(ref["failures"] or ref["n_metrics"] != 16 for ref in independent["references"]):
        raise ValueError("Source-native 16-band reference failure")
    quarantine = pd.read_csv(QUARANTINE)
    if len(quarantine) != 14 or int(quarantine.n_land_cells.sum()) != 450:
        raise ValueError("Seam plan changed")
    grid = pd.read_parquet(GRID, columns=["grid_id", "grid_x", "grid_y",
                                          "land_area_km2", "land_fraction"])
    seam_expected = set()
    pieces, manifest = [], []
    for plan in quarantine.itertuples(index=False):
        key = plan.tile_key
        _, x0, y0, size = key.split("_")
        if int(size) != 10:
            raise ValueError("Seam parent size changed")
        ids = set(grid.loc[grid.grid_x.between(int(x0),int(x0)+9) &
                           grid.grid_y.between(int(y0),int(y0)+9), "grid_id"])
        if len(ids) != int(plan.n_land_cells) or ids & seam_expected:
            raise ValueError("Seam parent expected membership overlapping/missing")
        seam_expected |= ids
        directory = OUT / key
        audit = json.loads((directory / "audit.json").read_text())
        path = directory / "merit_source_candidate.parquet"
        if (audit["status"] != "PARENT_EXACT_SOURCE_PIXEL_QC_PASS_GLOBAL_SEAM_APPROVAL_PENDING" or
            audit["tile_key"] != key or audit["GF10_SHA256"] != core.GRID_SHA or
            core.sha(path) != audit["output_sha256"]):
            raise ValueError("Seam parent source/QA fingerprint drift: " + key)
        frame = pd.read_parquet(path)
        if len(frame) != len(ids) or frame.grid_id.duplicated().any() or set(frame.grid_id) != ids:
            raise ValueError("Seam parent output ID mismatch: " + key)
        if set(frame.columns) != set(["grid_id"] + core.BANDS):
            raise ValueError("Seam output is not the frozen 16 indicators")
        frame["source_task_key"] = "SEAM_" + key
        pieces.append(frame)
        manifest.append({"tile_key": key, "n_GF10": len(frame),
                         "output_sha256": audit["output_sha256"],
                         "source_group_SHA256": {side:item["source_pixel_SHA256"]
                                                 for side,item in audit["source_groups"].items()}})
    result = pd.concat(pieces,ignore_index=True)
    if len(result) != 450 or result.grid_id.duplicated().any() or set(result.grid_id) != seam_expected:
        raise ValueError("450 seam GF10 not exactly conserved")
    # Two independent native-pixel requests and a separate grouped fetch must
    # yield the same 16 values for the original antimeridian cell.
    reference = json.loads((HERE / "seam_exact_source_-1737_-214.json").read_text())
    actual = result.set_index("grid_id").loc["-1737_-214"]
    for band, expected in reference["metrics"].items():
        if expected is not None and not math.isclose(float(actual[band]),float(expected),
                                                       rel_tol=1e-10,abs_tol=1e-8):
            raise ValueError("Independent grouped/source seam difference: " + band)
    historical = json.loads((HERE / "seam_native_pixel_diagnostic.json").read_text())
    if not math.isclose(float(actual.merit_hand_mean_m),
                        historical["raw_native_weighted_mean_m"],
                        rel_tol=1e-10,abs_tol=1e-8):
        raise ValueError("Earlier independent raw seam HAND reference differs")
    result = result.merge(grid,on="grid_id",how="left",validate="one_to_one")
    if result.land_area_km2.isna().any():
        raise ValueError("Seam output not mapped to frozen GF10 land")
    result = result[["grid_id", "grid_x", "grid_y", "land_area_km2",
                     "land_fraction", "source_task_key"] + core.BANDS]
    output = HERE / "merit_seam450_SOURCE_QC_PASS.parquet"
    result.to_parquet(output,index=False)
    report = {"status": "SEAM450_SOURCE_PIXEL_QC_PASS_FOR_GLOBAL_ASSEMBLY",
              "n_GF10": len(result), "n_parents": len(manifest),
              "frozen_GF10_SHA256": core.GRID_SHA,
              "independent_nonseam_all16_references": [r["grid_id"] for r in independent["references"]],
              "independent_seam_cell": "-1737_-214",
              "source_gap_rows": int(result.merit_valid_fraction.fillna(0).eq(0).sum()),
              "missing_per_band": {name:int(result[name].isna().sum()) for name in core.BANDS},
              "output": str(output), "output_sha256": core.sha(output),
              "source": "GEE MERIT/Hydro/v1_0_1 getPixels + computePixels",
              "boundary_method": "exact native pixel footprint intersection with original EPSG:6933 GF10",
              "parent_manifest": manifest,
              "GEE_seam_reduceRegion_disagreed_with_raw_source_and_was_not_used": True}
    (HERE / "merit_seam450_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__":
    report=main()
    print(json.dumps({k:v for k,v in report.items() if k!="parent_manifest"},indent=2))
