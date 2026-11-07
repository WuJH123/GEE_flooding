"""Compare all 16 raw/computed source-pixel metrics to accepted nonseam exports."""
import json

import pandas as pd
import rasterio

from merit_direct_raster_pilot import HERE, SITES, paths

import sys
sys.path.insert(0, r"E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106")
from cee_v8 import core  # noqa: E402

items = []
for site, gid in [("wuhan", "1080_350"), ("coast", "703_237")]:
    candidate = json.loads((HERE / ("seam_exact_source_" + gid + ".json")).read_text())
    directory, _, name = paths(site)
    audit = json.loads((directory / "audit.json").read_text())
    if audit["status"] != "SCIENTIFIC_QC_PASS_DIRECT_RASTER_PILOT":
        raise ValueError("Reference direct pilot not accepted")
    x, y = map(int, gid.split("_"))
    bx, by = SITES[site]
    with rasterio.open(directory / (name + ".tif")) as source:
        actual = source.read(masked=True)[:,by+60-y-1,x-bx]
    failures, differences = [], {}
    for name, value in candidate["metrics"].items():
        if value is None:
            continue
        estimate = float(actual[core.BANDS.index(name)])
        difference = abs(estimate-value)
        tolerance = (0.11 if name.startswith("merit_hand_p") else
                     max(0.002,abs(value)*0.0001))
        if "fraction" in name:
            tolerance = 0.001
        if name == "merit_upa_p90_km2":
            tolerance = max(0.001,abs(value)*0.0001)
        if name in ("merit_slope_mean_deg", "merit_slope_le2_fraction_valid"):
            tolerance = 0.02 if name.endswith("_deg") else 0.002
        differences[name] = {"raw_native": value, "accepted_direct": estimate,
                             "abs_diff": difference, "tolerance": tolerance}
        if difference > tolerance:
            failures.append(name)
    items.append({"grid_id": gid, "n_metrics": len(differences),
                  "failures": failures, "differences": differences})
gid = "-1720_679"
candidate = json.loads((HERE / ("seam_exact_source_" + gid + ".json")).read_text())
reference = pd.read_parquet(HERE / "native_merit_pilots" / "westedge_weighted" /
                            "native_science_candidate.parquet").set_index("grid_id").loc[gid]
failures, differences = [], {}
for name, value in candidate["metrics"].items():
    if value is None:
        continue
    estimate = float(reference[name])
    difference = abs(estimate-value)
    tolerance = (0.11 if name.startswith("merit_hand_p") else
                 max(0.002, abs(value)*0.0001))
    if "fraction" in name:
        tolerance = 0.001
    if name == "merit_upa_p90_km2":
        tolerance = max(0.001,abs(value)*0.0001)
    if name in ("merit_slope_mean_deg", "merit_slope_le2_fraction_valid"):
        tolerance = 0.02 if name.endswith("_deg") else 0.002
    differences[name] = {"raw_native": value, "accepted_native_weighted": estimate,
                         "abs_diff": difference, "tolerance": tolerance}
    if difference > tolerance:
        failures.append(name)
items.append({"grid_id": gid, "n_metrics": len(differences),
              "reference": "accepted_native_weighted_westedge",
              "failures": failures, "differences": differences})
report = {"status": "RAW_SOURCE_ALL_16_NON_SEAM_VALIDATION_PASS" if
          all(not item["failures"] for item in items) else
          "RAW_SOURCE_ALL_16_NON_SEAM_VALIDATION_FAIL",
          "references": items, "seam450_approved": False}
(HERE / "seam_source_16_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"status": report["status"],
                  "samples": [{"grid_id": item["grid_id"], "failures": item["failures"]}
                              for item in items]}, indent=2))
