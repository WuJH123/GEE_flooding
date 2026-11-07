"""Independent native MERIT source-pixel check for a wrapped GF10 seam cell."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import ee
import numpy as np
from pyproj import Transformer

ROOT = Path(r"E:\GEE_flooding")
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, eeops  # noqa: E402

ee.Initialize(project=core.PROJECT)
GRID_ID = "-1737_-214"
x, y = map(int, GRID_ID.split("_"))
segments = eeops.projected_seam_segments(x, y)
native = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").projection().getInfo()
sx, _, tx, _, sy, ty = native["transform"]
forward = Transformer.from_crs(6933, 4326, always_xy=True)
inverse = Transformer.from_crs(4326, 6933, always_xy=True)
all_values, all_weights = [], []
part_reports = []
for xa, ya, xb, yb in segments:
    lon0, lat0 = forward.transform(xa, ya)
    lon1, lat1 = forward.transform(xb, yb)
    if lon1 < lon0 or lat1 < lat0:
        raise ValueError("Wrapped segment coordinate order invalid")
    col0 = math.floor((lon0 - tx) / sx) - 1
    col1 = math.ceil((lon1 - tx) / sx) + 1
    row0 = math.floor((lat1 - ty) / sy) - 1
    row1 = math.ceil((lat0 - ty) / sy) + 1
    width, height = col1 - col0, row1 - row0
    if width * height > 1_000_000:
        raise ValueError("Unexpectedly large seam raw source request")
    request = {"assetId": "MERIT/Hydro/v1_0_1", "fileFormat": "NUMPY_NDARRAY",
               "bandIds": ["hnd"], "grid": {
                   "dimensions": {"width": width, "height": height},
                   "affineTransform": {"scaleX": sx, "shearX": 0,
                                       "translateX": tx + col0 * sx,
                                       "shearY": 0, "scaleY": sy,
                                       "translateY": ty + row0 * sy},
                   "crsCode": "EPSG:4326"}}
    raw = ee.data.getPixels(request)
    val = raw["hnd"] if raw.dtype.names else raw
    lon_edges = tx + np.arange(col0, col1 + 1) * sx
    lat_edges = ty + np.arange(row0, row1 + 1) * sy
    px, _ = inverse.transform(lon_edges, np.zeros_like(lon_edges))
    _, py = inverse.transform(np.zeros_like(lat_edges), lat_edges)
    wx = np.maximum(0, np.minimum(px[1:], xb) - np.maximum(px[:-1], xa))
    wy = np.maximum(0, np.minimum(py[:-1], yb) - np.maximum(py[1:], ya))
    weight = wy[:, None] * wx[None, :]
    valid = np.isfinite(val) & (val > -9990) & (weight > 0)
    all_values.append(np.asarray(val[valid], dtype=float))
    all_weights.append(np.asarray(weight[valid], dtype=float))
    part_reports.append({"projected_segment": [xa, ya, xb, yb],
                         "native_request_shape": [height, width],
                         "valid_pixels": int(valid.sum()),
                         "raw_native_valid_area_km2": float(weight[valid].sum()/1e6),
                         "raw_native_weighted_mean_m": float(np.average(val[valid],weights=weight[valid]))})
values = np.concatenate(all_values)
weights = np.concatenate(all_weights)
order = np.argsort(values, kind="stable")
values, weights = values[order], weights[order]
cdf = np.cumsum(weights) / weights.sum()
percentiles = {str(p): float(values[np.searchsorted(cdf, p / 100, side="left")])
               for p in (10, 50, 90)}
wkt = core.read_json(ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105" /
                     "config" / "recovery.json")["crs_wkt"]
geometry = eeops.rect(ee, x, y, wkt)
hnd = ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
reducer = ee.Reducer.mean().combine(
    ee.Reducer.percentile([10, 50, 90], maxRaw=150000), sharedInputs=True)
gee = hnd.reduceRegion(reducer, geometry, crs=hnd.projection(),
                       tileScale=8, maxPixels=200000).getInfo()
report = {"grid_id": GRID_ID, "segments": part_reports,
          "exact_projected_area_of_segments_km2": sum((xb-xa)*(yb-ya) for xa,ya,xb,yb in segments)/1e6,
          "raw_native_valid_area_km2": float(weights.sum()/1e6),
          "raw_native_weighted_mean_m": float(np.average(values, weights=weights)),
          "raw_native_weighted_percentiles_m": percentiles,
          "GEE_native_zonal": gee,
          "status": "SEAM_ONE_CELL_INDEPENDENT_DIAGNOSTIC_NOT_450_CELL_APPROVAL"}
path = ROOT / "CEE_GF10_COST_OPT_V10_20261106" / "seam_native_pixel_diagnostic.json"
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
