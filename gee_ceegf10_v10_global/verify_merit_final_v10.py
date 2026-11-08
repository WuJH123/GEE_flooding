"""Independent, whole-table GF10 and physical-invariant audit of MERIT product."""
from __future__ import annotations

import json
import math

import pandas as pd

from merit_direct_raster_pilot import HERE, ROOT
from plan_merit_hybrid_v10 import sha

import sys
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core  # noqa: E402


def main():
    product = HERE / "merit_hydro_GLOBAL_QC_PASS.parquet"
    prior = json.loads((HERE / "merit_global_assembly_report.json").read_text())
    grid_path = ROOT / "gee_ceegf10_v1/gf10_global_nonantarctic_land.parquet"
    if (prior["status"] != "GLOBAL_1395471_GF10_QC_PASS" or
        sha(product) != prior["output_sha256"] or sha(grid_path) != core.GRID_SHA):
        raise ValueError("Final MERIT/frozen GF10 fingerprint changed")
    frame = pd.read_parquet(product)
    grid = pd.read_parquet(grid_path, columns=["grid_id"])
    if len(frame) != core.GRID_ROWS or frame.grid_id.duplicated().any():
        raise ValueError("Final MERIT row count or ID uniqueness failed")
    if set(frame.grid_id.astype(str)) != set(grid.grid_id.astype(str)):
        raise ValueError("Final MERIT does not exactly cover frozen GF10 IDs")
    if list(frame.columns[-16:]) != core.BANDS:
        raise ValueError("MERIT 16-band order or schema changed")
    tests = {}
    for col in ("merit_valid_fraction", "merit_permanent_water_fraction",
                "merit_hand_le2_fraction_valid", "merit_hand_le5_fraction_valid",
                "merit_hand_le10_fraction_valid", "merit_slope_le2_fraction_valid"):
        bad = frame[col].dropna().lt(-1e-5) | frame[col].dropna().gt(1 + 1e-5)
        tests[col + "_outside_0_1"] = int(bad.sum())
    tests["negative_HAND_mean"] = int(frame.merit_hand_mean_m.dropna().lt(-1e-5).sum())
    tests["negative_UPA_mean"] = int(frame.merit_upa_mean_km2.dropna().lt(-1e-5).sum())
    tests["negative_UPA_max"] = int(frame.merit_upa_max_km2.dropna().lt(-1e-5).sum())
    tests["slope_outside_0_90"] = int((frame.merit_slope_mean_deg.dropna().lt(-1e-5) |
                                      frame.merit_slope_mean_deg.dropna().gt(90 + 1e-5)).sum())
    tests["HAND_quantile_not_monotone"] = int((
        frame.merit_hand_p10_m.gt(frame.merit_hand_p50_m + 1e-4) |
        frame.merit_hand_p50_m.gt(frame.merit_hand_p90_m + 1e-4)).sum())
    tests["HAND_threshold_fraction_not_nested"] = int((
        frame.merit_hand_le2_fraction_valid.gt(frame.merit_hand_le5_fraction_valid + 1e-5) |
        frame.merit_hand_le5_fraction_valid.gt(frame.merit_hand_le10_fraction_valid + 1e-5)).sum())
    tests["UPA_mean_exceeds_max"] = int(frame.merit_upa_mean_km2.gt(
        frame.merit_upa_max_km2 + 1e-3).sum())
    expected_log = frame.merit_upa_max_km2.clip(lower=0).map(math.log1p)
    tests["UPA_log1p_mismatch"] = int((frame.merit_upa_max_log1p - expected_log).abs().gt(1e-3).sum())
    if any(tests.values()):
        raise ValueError("Final MERIT physical invariant failure: " + str(tests))
    report = {"status": "INDEPENDENT_GLOBAL_MERIT_QC_PASS",
              "frozen_GF10": core.GRID_ROWS, "exact_ID_coverage": True,
              "metric_bands_in_frozen_order": core.BANDS,
              "source_gap_rows": int(frame.merit_valid_fraction.fillna(0).eq(0).sum()),
              "missing_per_band": {band: int(frame[band].isna().sum()) for band in core.BANDS},
              "physical_constraint_failures": tests,
              "output_sha256": sha(product)}
    (HERE / "merit_independent_post_assembly_qc.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
