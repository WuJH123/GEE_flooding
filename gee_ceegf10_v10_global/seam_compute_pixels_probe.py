"""Read-only raw asset versus computed-image pixel identity at the seam."""
import json
import math
from pathlib import Path
import sys

import ee
import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\GEE_flooding")
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import eeops  # noqa: E402

segments = eeops.projected_seam_segments(-1737, -214)
ee.Initialize(project="future-shuttle-513705-g9")
source = ee.Image("MERIT/Hydro/v1_0_1")
sx, _, tx, _, sy, ty = source.select("hnd").projection().getInfo()["transform"]
forward = Transformer.from_crs(6933, 4326, always_xy=True)
xa, ya, xb, yb = segments[0]
lon0, lat0 = forward.transform(xa, ya)
lon1, lat1 = forward.transform(xb, yb)
col0 = math.floor((lon0 - tx) / sx) - 1
col1 = math.ceil((lon1 - tx) / sx) + 1
row0 = math.floor((lat1 - ty) / sy) - 1
row1 = math.ceil((lat0 - ty) / sy) + 1
grid = {"dimensions": {"width": col1-col0, "height": row1-row0},
        "affineTransform": {"scaleX": sx, "shearX": 0,
                            "translateX": tx+col0*sx,
                            "shearY": 0, "scaleY": sy,
                            "translateY": ty+row0*sy}, "crsCode": "EPSG:4326"}
raw = ee.data.getPixels({"assetId": "MERIT/Hydro/v1_0_1",
                         "fileFormat": "NUMPY_NDARRAY", "bandIds": ["hnd"],
                         "grid": grid})["hnd"]
computed = ee.data.computePixels({"expression": source.select("hnd"),
                                  "fileFormat": "NUMPY_NDARRAY", "bandIds": ["hnd"],
                                  "grid": grid})["hnd"]
slope = ee.data.computePixels({"expression": ee.Terrain.slope(source.select("elv")).rename("slope"),
                               "fileFormat": "NUMPY_NDARRAY", "bandIds": ["slope"],
                               "grid": grid})["slope"]
valid = np.isfinite(raw) & (raw > -9990) & np.isfinite(computed) & (computed > -9990)
report = {"status": "ONE_SEAM_SEGMENT_COMPUTE_PIXELS_READ_ONLY",
          "grid_dimensions": grid["dimensions"],
          "raw_valid": int((np.isfinite(raw)&(raw>-9990)).sum()),
          "computed_valid": int((np.isfinite(computed)&(computed>-9990)).sum()),
          "joint_valid": int(valid.sum()),
          "raw_vs_computed_max_abs": float(np.abs(raw[valid]-computed[valid]).max()),
          "slope_valid": int((np.isfinite(slope)&(slope>-9990)).sum()),
          "seam450_still_quarantined": True}
(HERE / "seam_compute_pixels_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
