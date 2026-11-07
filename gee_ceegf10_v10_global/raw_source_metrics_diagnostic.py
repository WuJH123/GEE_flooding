"""Independent area-weighted native MERIT source-pixel statistics for one GF10.

Reads the immutable source asset via getPixels, separately from the production
reduceRegions expression. This diagnostic never submits a batch task.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import ee
import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
PROJECT = "future-shuttle-513705-g9"
parser = argparse.ArgumentParser()
parser.add_argument("--grid-id", required=True)
args = parser.parse_args()
gid = args.grid_id
x, y = map(int, gid.split("_"))
ee.Initialize(project=PROJECT)
src = ee.Image("MERIT/Hydro/v1_0_1")
proj = src.select("hnd").projection().getInfo()
sx, _, tx, _, sy, ty = proj["transform"]
forward = Transformer.from_crs(6933, 4326, always_xy=True)
inverse = Transformer.from_crs(4326, 6933, always_xy=True)
lon0, lat0 = forward.transform(x*10000, y*10000)
lon1, lat1 = forward.transform((x+1)*10000, (y+1)*10000)
if not (math.isfinite(lon0) and math.isfinite(lon1) and lon0 < lon1 and lat0 < lat1):
    raise ValueError("Nonseam GF10 source geometry expected")
col0, col1 = math.floor((lon0-tx)/sx)-1, math.ceil((lon1-tx)/sx)+1
row0, row1 = math.floor((lat1-ty)/sy)-1, math.ceil((lat0-ty)/sy)+1
width, height = col1-col0, row1-row0
if width*height > 200000 or width <= 0 or height <= 0:
    raise ValueError("Source-native diagnostic exceeds independently audited pixel bound")
bands = ["hnd", "elv", "upa", "wat"]
request = {"assetId": "MERIT/Hydro/v1_0_1", "fileFormat": "NUMPY_NDARRAY",
           "bandIds": bands,
           "grid": {"dimensions": {"width": width, "height": height},
                    "affineTransform": {"scaleX": sx, "shearX": 0,
                                        "translateX": tx+col0*sx,
                                        "shearY": 0, "scaleY": sy,
                                        "translateY": ty+row0*sy},
                    "crsCode": "EPSG:4326"}}
raw = ee.data.getPixels(request)
lon_edges = tx + np.arange(col0, col1+1)*sx
lat_edges = ty + np.arange(row0, row1+1)*sy
xx, _ = inverse.transform(lon_edges, np.zeros_like(lon_edges))
_, yy = inverse.transform(np.zeros_like(lat_edges), lat_edges)
wx = np.maximum(0, np.minimum(xx[1:],(x+1)*10000)-np.maximum(xx[:-1],x*10000))
wy = np.maximum(0, np.minimum(yy[:-1],(y+1)*10000)-np.maximum(yy[1:],y*10000))
weights = wx[None,:]*wy[:,None]
inside = weights > 0


def valid_array(name):
    arr = np.asarray(raw[name], dtype=float)
    valid = inside & np.isfinite(arr) & (arr > -9990)
    return arr, valid


def mean(name):
    values, valid = valid_array(name)
    return float(np.average(values[valid], weights=weights[valid])) if valid.any() else None


def percentile(name, p):
    values, valid = valid_array(name)
    if not valid.any():
        return None
    order = np.argsort(values[valid], kind="stable")
    v, w = values[valid][order], weights[valid][order]
    return float(v[np.searchsorted(np.cumsum(w)/w.sum(),p/100,side="left")])


hnd, hv = valid_array("hnd")
upa, uv = valid_array("upa")
wat, wv = valid_array("wat")
full_area = 100_000_000.0
report = {"status":"INDEPENDENT_SOURCE_PIXEL_METRICS_NOT_GLOBAL_APPROVAL",
          "grid_id":gid,"source":"MERIT/Hydro/v1_0_1",
          "native_projection":proj,"raw_request_shape":[height,width],
          "source_intersection_pixel_count":int(inside.sum()),
          "metrics":{
              "merit_hand_mean_m":mean("hnd"),
              "merit_elv_mean_m":mean("elv"),
              "merit_upa_mean_km2":mean("upa"),
              # getPixels fills masked wat outside the MERIT footprint with
              # zero; the scientific water fraction denominator is the native
              # MERIT-valid footprint (hnd and wat masks checked equal in EE).
              "merit_permanent_water_fraction":float(np.average(wat[hv]==1,weights=weights[hv])) if hv.any() else None,
              "merit_valid_fraction":float(weights[hv].sum()/full_area),
              "merit_hand_le2_fraction_valid":float(np.average(hnd[hv]<=2,weights=weights[hv])) if hv.any() else None,
              "merit_hand_le5_fraction_valid":float(np.average(hnd[hv]<=5,weights=weights[hv])) if hv.any() else None,
              "merit_hand_le10_fraction_valid":float(np.average(hnd[hv]<=10,weights=weights[hv])) if hv.any() else None,
              "merit_upa_max_km2":float(upa[uv].max()) if uv.any() else None,
              "merit_hand_p10_m":percentile("hnd",10),
              "merit_hand_p50_m":percentile("hnd",50),
              "merit_hand_p90_m":percentile("hnd",90),
              "merit_upa_p90_km2":percentile("upa",90),
          },
          "slope_must_be_checked_separately_against_original_graph":True}
report["water_denominator"] = "MERIT_native_valid_HND_mask_equal_to_WAT_mask_in_source_probe"
target = HERE / f"raw_source_metrics_{gid}.json"
target.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({"grid_id":gid,"status":report["status"],
                  "raw_request_shape":report["raw_request_shape"]}))
