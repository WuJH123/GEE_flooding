"""Four-region source-pixel QC for all 16 direct-raster graph outputs."""
import json
import math
import sys

import ee
import pandas as pd

from merit_direct_raster_pilot import HERE, ROOT, image

sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core  # noqa: E402

wkt = json.loads((ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/config/recovery.json").read_text())["crs_wkt"]
ee.Initialize(project=core.PROJECT)
raster = image(ee, wkt)
transform = [10000, 0, 0, 0, -10000, 0]
v7 = pd.read_parquet(
    ROOT / "CEE_GF10_FIG1_AUDIT_GEE_V7_20261106/data/merit_v7_batch5_accepted_partial.parquet"
).set_index("grid_id")
report = {"status": "DIRECT_RASTER_16_BAND_FOUR_REGION_SOURCE_QC_NOT_LIVE_EXPORT_APPROVAL",
          "source": "MERIT/Hydro/v1_0_1", "source_percentile_maxRaw": 150000, "GF10": []}
for gid in ["1080_350", "703_237", "1090_360", "-1720_679"]:
    x, y = map(int, gid.split("_"))
    geometry = ee.Geometry.Rectangle(
        [x*10000, y*10000, (x+1)*10000, (y+1)*10000], proj=wkt, geodesic=False)
    actual = raster.reduceRegion(
        ee.Reducer.first(), geometry, crs=wkt, crsTransform=transform, maxPixels=20).getInfo()
    if set(actual) != set(core.BANDS):
        raise ValueError("Direct graph did not yield exactly 16 frozen metrics")
    path = HERE / f"raw_source_metrics_{gid}.json"
    raw = json.loads(path.read_text())["metrics"]
    failures, diffs = [], {}
    for name, reference in raw.items():
        if reference is None:
            continue
        value = float(actual[name])
        difference = abs(value-reference)
        tolerance = (0.11 if name.startswith("merit_hand_p") else
                     max(0.002, 0.0001*abs(reference)))
        if "fraction" in name:
            tolerance = 0.001
        if name == "merit_upa_p90_km2":
            tolerance = max(0.001, 0.0001*abs(reference))
        diffs[name] = {"direct_GF10": value, "raw_source": reference,
                       "absolute_difference": difference, "tolerance": tolerance}
        if difference > tolerance:
            failures.append(name)
    derived_log_abs = abs(actual["merit_upa_max_log1p"] -
                          math.log1p(max(0, actual["merit_upa_max_km2"])))
    if derived_log_abs > 1e-5:
        failures.append("merit_upa_max_log1p")
    slope_ref = None
    if gid in v7.index:
        slope_ref = {name: float(v7.loc[gid, name]) for name in
                     ["merit_slope_mean_deg", "merit_slope_le2_fraction_valid"]}
    item = {"grid_id": gid, "n_frozen_bands": len(actual),
            "n_independent_raw_source_metrics": len(diffs),
            "source_pixel_differences": diffs,
            "slope_graph_outputs": {name: actual[name] for name in
                                    ["merit_slope_mean_deg", "merit_slope_le2_fraction_valid"]},
            "slope_v7_reference": slope_ref,
            "log1p_derivation_absolute_difference": derived_log_abs,
            "failed_metrics": failures, "raw_source_sha256": core.sha(path)}
    report["GF10"].append(item)
    print(json.dumps({"grid_id": gid, "raw_metrics": len(diffs),
                      "failures": failures}), flush=True)
report["source_pixel_13_metric_QC_pass"] = all(not x["failed_metrics"] for x in report["GF10"])
(HERE / "raster_direct_16_source_qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
