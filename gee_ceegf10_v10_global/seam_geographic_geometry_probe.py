"""Read-only 1-GF10 antimeridian geometry probe; never submits a batch task."""
import json
from pathlib import Path
import sys

import ee
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\GEE_flooding")
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import eeops  # noqa: E402

GRID_ID = "-1737_-214"
x, y = map(int, GRID_ID.split("_"))
segments = eeops.projected_seam_segments(x, y)
ee.Initialize(project="future-shuttle-513705-g9")
forward = Transformer.from_crs(6933, 4326, always_xy=True)
hnd = ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
area = ee.Image.pixelArea()
numden = ee.Image.cat([hnd.multiply(area).rename("num"),
                       area.updateMask(hnd.mask()).rename("den")])
raw = json.loads((HERE / "seam_native_pixel_diagnostic.json").read_text())
results = []
for xa, ya, xb, yb in segments:
    lon0, lat0 = forward.transform(xa, ya)
    lon1, lat1 = forward.transform(xb, yb)
    geom = ee.Geometry.Rectangle([lon0, lat0, lon1, lat1], proj="EPSG:4326",
                                 geodesic=False)
    sums = numden.reduceRegion(ee.Reducer.sum(), geom, crs=hnd.projection(),
                               tileScale=8, maxPixels=500000).getInfo()
    results.append({"box_lonlat": [lon0, lat0, lon1, lat1],
                    "GEE_geographic_rect_mean_m": sums["num"] / sums["den"],
                    "GEE_geographic_rect_area_km2": sums["den"] / 1e6})
report = {"status": "ONE_CELL_READ_ONLY_GEOGRAPHIC_GEOMETRY_PROBE",
          "grid_id": GRID_ID, "results": results,
          "raw_source_segments": raw["segments"],
          "450_seam_GF10_still_quarantined": True}
(HERE / "seam_geographic_geometry_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
