"""Independent all-16 MERIT source-pixel estimator for one frozen GF10.

All remote work is an Earth Engine raw/computed pixel request. The local step
intersects the native pixel footprints with the exact EPSG:6933 GF10 cell.
No result from this diagnostic enters the approved global wide table.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import ee
import numpy as np
from pyproj import Transformer

ROOT = Path(r"E:\GEE_flooding")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, eeops  # noqa: E402


def weighted_percentile(values, weights, percentile):
    if not len(values):
        return None
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    cdf = np.cumsum(weights[order]) / weights.sum()
    return float(sorted_values[np.searchsorted(cdf, percentile/100, side="left")])


def one_cell(gid: str, ee_module=ee) -> dict:
    x, y = map(int, gid.split("_"))
    src = ee_module.Image("MERIT/Hydro/v1_0_1")
    sx, _, tx, _, sy, ty = src.select("hnd").projection().getInfo()["transform"]
    forward = Transformer.from_crs(6933, 4326, always_xy=True)
    inverse = Transformer.from_crs(4326, 6933, always_xy=True)
    slope = ee_module.Terrain.slope(src.select("elv")).rename("slope")
    slope_image = ee_module.Image.cat([slope, slope.mask().rename("slope_mask")])
    parts = []
    for xa, ya, xb, yb in eeops.projected_seam_segments(x, y):
        lon0, lat0 = forward.transform(xa, ya)
        lon1, lat1 = forward.transform(xb, yb)
        if not (math.isfinite(lon0) and math.isfinite(lon1) and lon0 < lon1 and lat0 < lat1):
            raise ValueError("Illegal source native seam geometry")
        c0, c1 = math.floor((lon0-tx)/sx)-1, math.ceil((lon1-tx)/sx)+1
        r0, r1 = math.floor((lat1-ty)/sy)-1, math.ceil((lat0-ty)/sy)+1
        width, height = c1-c0, r1-r0
        if not (0 < width*height <= 200000):
            raise ValueError("One-cell native pixel request exceeds verified 200k bound")
        grid = {"dimensions": {"width": width, "height": height},
                "affineTransform": {"scaleX": sx, "shearX": 0,
                                    "translateX": tx+c0*sx,
                                    "shearY": 0, "scaleY": sy,
                                    "translateY": ty+r0*sy}, "crsCode": "EPSG:4326"}
        raw = ee_module.data.getPixels({"assetId": "MERIT/Hydro/v1_0_1",
                                        "fileFormat": "NUMPY_NDARRAY",
                                        "bandIds": ["hnd", "elv", "upa", "wat"],
                                        "grid": grid})
        gradient = ee_module.data.computePixels({"expression": slope_image,
                                                  "fileFormat": "NUMPY_NDARRAY",
                                                  "bandIds": ["slope", "slope_mask"],
                                                  "grid": grid})
        lon_edges = tx + np.arange(c0, c1+1)*sx
        lat_edges = ty + np.arange(r0, r1+1)*sy
        px, _ = inverse.transform(lon_edges, np.zeros_like(lon_edges))
        _, py = inverse.transform(np.zeros_like(lat_edges), lat_edges)
        wx = np.maximum(0, np.minimum(px[1:], xb)-np.maximum(px[:-1], xa))
        wy = np.maximum(0, np.minimum(py[:-1], yb)-np.maximum(py[1:], ya))
        weight = wy[:, None]*wx[None, :]
        inside = weight > 0
        hnd = np.asarray(raw["hnd"], dtype=float)
        valid = inside & np.isfinite(hnd) & (hnd > -9990)
        slope_values = np.asarray(gradient["slope"], dtype=float)
        slope_valid = inside & (np.asarray(gradient["slope_mask"], dtype=float) > 0)
        parts.append({"raw": raw, "hnd": hnd, "valid": valid,
                      "slope": slope_values, "slope_valid": slope_valid,
                      "weight": weight, "source_pixels": int(inside.sum()),
                      "segment": [xa, ya, xb, yb]})
    def arrays(name, use_hnd_mask=False):
        values, weights = [], []
        for part in parts:
            arr = part["slope"] if name == "slope" else np.asarray(part["raw"][name], dtype=float)
            valid = part["slope_valid"] if name == "slope" else part["valid"] if use_hnd_mask else (
                (part["weight"] > 0) & np.isfinite(arr) & (arr > -9990))
            values.append(arr[valid])
            weights.append(part["weight"][valid])
        return np.concatenate(values), np.concatenate(weights)
    def average(name, use_hnd_mask=False):
        values, weights = arrays(name, use_hnd_mask)
        return float(np.average(values, weights=weights)) if len(values) else None
    hnd, wh = arrays("hnd")
    upa, wu = arrays("upa")
    water, ww = arrays("wat", True)
    grad, wg = arrays("slope")
    if len(water) != len(hnd) or not np.array_equal(wh, ww):
        raise ValueError("MERIT water/HAND source mask differs")
    if wh.sum() > 100000000.01:
        raise ValueError("Seam periodic segments double-count GF10 area")
    metrics = {
        "merit_hand_mean_m": average("hnd"),
        "merit_elv_mean_m": average("elv"),
        "merit_upa_mean_km2": average("upa"),
        "merit_permanent_water_fraction": float(np.average(water==1, weights=ww)) if len(water) else None,
        "merit_valid_fraction": float(wh.sum()/100000000),
        "merit_hand_le2_fraction_valid": float(np.average(hnd<=2, weights=wh)) if len(hnd) else None,
        "merit_hand_le5_fraction_valid": float(np.average(hnd<=5, weights=wh)) if len(hnd) else None,
        "merit_hand_le10_fraction_valid": float(np.average(hnd<=10, weights=wh)) if len(hnd) else None,
        "merit_slope_mean_deg": float(np.average(grad, weights=wg)) if len(grad) else None,
        "merit_slope_le2_fraction_valid": float(np.average(grad<=2, weights=wg)) if len(grad) else None,
        "merit_upa_max_km2": float(upa.max()) if len(upa) else None,
        "merit_upa_max_log1p": math.log1p(max(0, float(upa.max()))) if len(upa) else None,
        "merit_hand_p10_m": weighted_percentile(hnd, wh, 10),
        "merit_hand_p50_m": weighted_percentile(hnd, wh, 50),
        "merit_hand_p90_m": weighted_percentile(hnd, wh, 90),
        "merit_upa_p90_km2": weighted_percentile(upa, wu, 90),
    }
    if set(metrics) != set(core.BANDS):
        raise ValueError("Frozen MERIT 16-band contract changed")
    return {"status": "INDEPENDENT_NATIVE_SOURCE_PIXEL_CANDIDATE_NOT_SEAM_APPROVED",
            "grid_id": gid, "source": "MERIT/Hydro/v1_0_1",
            "source_valid_area_km2": float(wh.sum()/1e6),
            "segment_count": len(parts),
            "source_pixels_intersecting": sum(part["source_pixels"] for part in parts),
            "metrics": metrics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-id", required=True)
    args = parser.parse_args()
    ee.Initialize(project=core.PROJECT)
    report = one_cell(args.grid_id)
    path = HERE / ("seam_exact_source_" + args.grid_id + ".json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"grid_id": args.grid_id, "status": report["status"],
                      "source_valid_area_km2": report["source_valid_area_km2"],
                      "segment_count": report["segment_count"]}))
