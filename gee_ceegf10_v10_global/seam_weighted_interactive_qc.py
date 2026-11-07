"""One original GF10 antimeridian cell, weighted source-pixel cross-check."""
import json
import sys
from pathlib import Path

import ee

ROOT = Path(r"E:\GEE_flooding")
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import eeops  # noqa: E402

gid="-1737_-214"
x,y=map(int,gid.split("_"))
wkt=json.loads((ROOT/"CEE_GF10_GEE_RECOVERY_V4_20261105"/
                "config"/"recovery.json").read_text())["crs_wkt"]
ee.Initialize(project="future-shuttle-513705-g9")
geometry=eeops.rect(ee,x,y,wkt)
hnd=ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
area=ee.Image.pixelArea()
numden=ee.Image.cat([hnd.multiply(area).rename("num"),
                     area.updateMask(hnd.mask()).rename("den")])
sums=numden.reduceRegion(ee.Reducer.sum(),geometry,crs=hnd.projection(),
                         tileScale=8,maxPixels=500000).getInfo()
percent=hnd.reduceRegion(ee.Reducer.percentile([10,50,90],maxRaw=150000),
                         geometry,crs=hnd.projection(),tileScale=8,
                         maxPixels=250000).getInfo()
independent=json.loads((HERE/"seam_native_pixel_diagnostic.json").read_text())
actual={"mean":sums["num"]/sums["den"],
        "p10":percent["hnd_p10"],"p50":percent["hnd_p50"],"p90":percent["hnd_p90"]}
raw={"mean":independent["raw_native_weighted_mean_m"]}
raw.update({"p"+k:v for k,v in independent["raw_native_weighted_percentiles_m"].items()})
report={"status":"ONE_SEAM_GF10_INTERACTIVE_SOURCE_QC_NOT_450_CELL_APPROVAL",
        "grid_id":gid,"original_grid_id_preserved":True,
        "geometry":"periodic_two_polygon_from_original_6933_cell",
        "pixel_area_weighted_GEE":actual,"independent_raw_source_pixels":raw,
        "absolute_differences":{k:abs(actual[k]-raw[k]) for k in actual},
        "seam450_still_quarantined":True}
(HERE/"seam_weighted_interactive_qc.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
