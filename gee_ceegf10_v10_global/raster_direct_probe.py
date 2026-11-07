"""Read-only low-cost direct native->GF10 raster aggregation diagnostic."""
import json
from pathlib import Path

import ee

ROOT=Path(r"E:\GEE_flooding")
HERE=Path(__file__).resolve().parent
wkt=json.loads((ROOT/"CEE_GF10_GEE_RECOVERY_V4_20261105"/
                "config"/"recovery.json").read_text())["crs_wkt"]
ee.Initialize(project="future-shuttle-513705-g9")
src=ee.Image("MERIT/Hydro/v1_0_1")
hnd=src.select("hnd");upa=src.select("upa");area=ee.Image.pixelArea()
transform=[10000,0,0,0,-10000,0]
output={}
for gid in ["1080_350","703_237","1090_360","-1720_679","-500_723"]:
    x,y=map(int,gid.split("_"))
    g=ee.Geometry.Rectangle([x*10000,y*10000,(x+1)*10000,(y+1)*10000],
                            proj=wkt,geodesic=False)
    values={}
    for name,img,reducer in [
            ("hnd_mean",hnd,ee.Reducer.mean()),
            ("upa_mean",upa,ee.Reducer.mean()),
            ("hnd_percent",hnd,ee.Reducer.percentile([10,50,90],maxRaw=150000)),
            ("upa_p90",upa,ee.Reducer.percentile([90],maxRaw=150000))]:
        try:
            raster=img.reduceResolution(reducer,bestEffort=False,maxPixels=65536).reproject(
                crs=wkt,crsTransform=transform)
            val=raster.reduceRegion(ee.Reducer.first(),g,crs=wkt,
                                    crsTransform=transform,maxPixels=10).getInfo()
            values[name]={"status":"PASS","result":val}
        except Exception as exc:
            values[name]={"status":"FAIL","error":str(exc)[:400]}
    raw=json.loads((HERE/f"raw_source_metrics_{gid}.json").read_text())["metrics"]
    output[gid]={"results":values,"raw_source":raw}
    print(json.dumps({"grid_id":gid,"status":{k:v["status"] for k,v in values.items()}}),flush=True)
report={"status":"INTERACTIVE_DIRECT_RASTER_PROBE_NOT_PRODUCTION_APPROVAL",
        "maxRaw":150000,"maxPixels":65536,"source":"MERIT/Hydro/v1_0_1",
        "cells":output}
(HERE/"raster_direct_probe.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
