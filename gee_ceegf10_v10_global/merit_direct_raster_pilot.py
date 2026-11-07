"""One 6x6-parent MERIT direct native->10 km raster export pilot.

Source-native means and maxRaw percentiles matched independently downloaded
source pixels in five GF10 probes. A real export/QC and EECU check are still
required before this much cheaper route can replace the zonal candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import ee
import pandas as pd

ROOT=Path(r"E:\GEE_flooding")
HERE=ROOT/"CEE_GF10_COST_OPT_V10_20261106"
sys.path.insert(0,str(ROOT/"CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, eeops  # noqa: E402

SITES={"wuhan":(1080,350),"coast":(700,220),"westedge":(-1720,640)}
FOLDER="CEE_GF10_MERIT_DIRECT_V10_20261107"
SIZE=60


def source(site):
    path=ROOT/"gee_ceegf10_v1"/"gf10_global_nonantarctic_land.parquet"
    if core.sha(path)!=core.GRID_SHA:
        raise ValueError("Frozen GF10 SHA changed")
    x,y=SITES[site]
    frame=pd.read_parquet(path,columns=["grid_id","grid_x","grid_y"])
    frame=frame.loc[frame.grid_x.between(x,x+SIZE-1)&
                    frame.grid_y.between(y,y+SIZE-1)].copy()
    if not 1<=len(frame)<=SIZE*SIZE or frame.grid_id.duplicated().any():
        raise ValueError("GF10 direct-raster pilot source membership invalid")
    return frame


def image(ee,wkt):
    src=ee.Image("MERIT/Hydro/v1_0_1")
    hnd,upa=src.select("hnd"),src.select("upa")
    slope=ee.Terrain.slope(src.select("elv"))
    stats=ee.Image.cat([hnd,src.select("elv"),upa,src.select("wat").eq(1),
                        hnd.mask().unmask(0),hnd.lte(2),hnd.lte(5),hnd.lte(10),
                        slope,slope.lte(2)]).rename(core.BANDS[:10])
    transform=[10000,0,0,0,-10000,0]
    def direct(source,reducer):
        return source.reduceResolution(reducer,bestEffort=False,
                                       maxPixels=65536).reproject(
                                           crs=wkt,crsTransform=transform)
    means=direct(stats,ee.Reducer.mean())
    maximum=direct(upa,ee.Reducer.max()).rename(core.BANDS[10])
    logmax=maximum.max(0).add(1).log().rename(core.BANDS[11])
    hand_percent=direct(hnd,ee.Reducer.percentile([10,50,90],
                                                  maxRaw=150000)).rename(core.BANDS[12:15])
    upa_p90=direct(upa,ee.Reducer.percentile([90],maxRaw=150000)).rename(core.BANDS[15])
    return ee.Image.cat([means,maximum,logmax,hand_percent,upa_p90]).toFloat().rename(core.BANDS)


def paths(site):
    x,y=SITES[site]
    name=f"CEE_GF10_MERIT_DIRECT_V10_P6_{site.upper()}_{x}_{y}"
    directory=HERE/"merit_direct_pilots"/site
    return directory,directory/"intent.json",name


def main(site,execute):
    frame=source(site)
    directory,intent_path,name=paths(site)
    x,y=SITES[site]
    if not execute:
        print(json.dumps({"status":"DRY_RUN_NO_GEE_SUBMISSION","name":name,
                          "n_land_GF10":len(frame),"output_shape":[60,60],
                          "source_pixel_cap_per_10km_output":65536,
                          "source_native_direct_percentile_maxRaw":150000,
                          "real_export_and_EECU_pending":True}))
        return
    if intent_path.exists():
        raise RuntimeError("Existing immutable intent; no duplicate direct raster task")
    ee.Initialize(project=core.PROJECT)
    if any(z.get("description")==name for z in ee.data.getTaskList()):
        raise RuntimeError("GEE already has exact direct-raster task description")
    wkt=core.read_json(ROOT/"CEE_GF10_GEE_RECOVERY_V4_20261105"/
                       "config"/"recovery.json")["crs_wkt"]
    bbox=[x*10000,y*10000,(x+SIZE)*10000,(y+SIZE)*10000]
    region=ee.Geometry.Rectangle(eeops.merit_export_interior(bbox),
                                 proj=wkt,geodesic=False)
    task=ee.batch.Export.image.toDrive(
        image=image(ee,wkt).unmask(-9999),description=name,
        folder=FOLDER,fileNamePrefix=name,region=region,crs=wkt,
        crsTransform=[10000,0,0,0,-10000,0],maxPixels=SIZE*SIZE,
        fileFormat="GeoTIFF",formatOptions={"cloudOptimized":True,"noData":-9999})
    directory.mkdir(parents=True,exist_ok=True)
    input_file=directory/"input_GF10.parquet"
    frame.to_parquet(input_file,index=False)
    intent={"state":"SUBMISSION_INTENT","name":name,"grid_SHA256":core.GRID_SHA,
            "input_SHA256":core.sha(input_file),"n_land_GF10":len(frame),
            "site":site,"science_graph":"DIRECT_SOURCE_TO_GF10_MAXRAW150000",
            "source_metric_sample_QC":"raster_direct_probe.json",
            "global_approved":False}
    core.write_json(intent_path,intent)
    task.start()
    intent.update(state="SUBMITTED_NOT_QC",task_id=task.id)
    core.write_json(intent_path,intent)
    print(json.dumps({"state":"SUBMITTED_NOT_QC","task_id":task.id,"name":name}))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",choices=sorted(SITES),required=True)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    main(args.site,args.execute)
