"""Real Drive GeoTIFF and independent source-pixel QC for direct MERIT pilot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import ee
import pandas as pd
import rasterio

from merit_direct_raster_pilot import ROOT, HERE, SITES, SIZE, paths

sys.path.insert(0,str(ROOT/"CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, download, qc  # noqa: E402

REFERENCES={"wuhan":["1080_350"],"coast":["703_237"],
            "westedge":["-1720_679"]}


def audit(site):
    directory,intent_path,name=paths(site)
    intent=core.read_json(intent_path)
    frame=pd.read_parquet(directory/"input_GF10.parquet")
    if intent["name"]!=name or intent["input_SHA256"]!=core.sha(directory/"input_GF10.parquet"):
        raise ValueError("Direct MERIT immutable pilot input changed")
    ee.Initialize(project=core.PROJECT)
    status=ee.data.getTaskStatus([intent["task_id"]])[0]
    report={"site":site,"task_id":intent["task_id"],"GEE_state":status["state"],
            "scientifically_accepted":False,"source_graph":intent["science_graph"]}
    if status["state"]!="COMPLETED":
        report.update(status=("GEE_FAILED" if status["state"] in ("FAILED","CANCELLED")
                              else "GEE_PENDING"),error=status.get("error_message"))
    else:
        operation=ee.data.getOperation(status["name"])
        seconds=(operation.get("metadata") or {}).get("batchEecuUsageSeconds")
        if seconds is None:
            report["status"]="GEE_SUCCEEDED_EECU_PENDING"
        else:
            report["actual_eecu_h"]=float(seconds)/3600
            path=download.get_source(name,directory,"drive",kind="merit")
            if path is None:
                report["status"]="GEE_SUCCEEDED_DRIVE_FILE_PENDING"
            else:
                x,y=SITES[site]
                row=pd.Series({"crop_x0":x,"crop_y0":y,"width":SIZE,"height":SIZE,
                               "n_land_cells":len(frame),
                               "land_ids":";".join(sorted(frame.grid_id.astype(str)))})
                report["engineering_QC"]=qc.merit(path,row)
                independent=[]
                with rasterio.open(path) as ds:
                    for gid in REFERENCES[site]:
                        gx,gy=map(int,gid.split("_"))
                        values=ds.read(masked=True)[:,y+SIZE-gy-1,gx-x]
                        raw=json.loads((HERE/f"raw_source_metrics_{gid}.json").read_text())
                        failures=[];differences={}
                        for band,reference in raw["metrics"].items():
                            if reference is None:continue
                            actual=float(values[core.BANDS.index(band)])
                            delta=abs(actual-reference)
                            tolerance=(0.11 if band.startswith("merit_hand_p") else
                                       max(0.002,abs(reference)*0.0001))
                            if "fraction" in band:tolerance=0.001
                            if band=="merit_upa_p90_km2":tolerance=max(0.001,abs(reference)*0.0001)
                            differences[band]={"GEE":actual,"raw_source":reference,
                                               "abs_diff":delta,"tolerance":tolerance}
                            if delta>tolerance:failures.append(band)
                        independent.append({"grid_id":gid,"differences":differences,
                                            "failed_bands":failures,
                                            "source_report_sha256":core.sha(HERE/f"raw_source_metrics_{gid}.json")})
                report["independent_source_pixel_QC"]=independent
                report["status"]=("SCIENTIFIC_QC_PASS_DIRECT_RASTER_PILOT" if
                                  all(not z["failed_bands"] for z in independent) else
                                  "SCIENTIFIC_QC_FAIL_SOURCE_PIXEL_DIFFERENCE")
                report["scientifically_accepted"]=report["status"].startswith("SCIENTIFIC_QC_PASS")
    directory.mkdir(parents=True,exist_ok=True)
    core.write_json(directory/"audit.json",report)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",choices=sorted(SITES),required=True)
    args=parser.parse_args()
    result=audit(args.site)
    print(json.dumps({k:v for k,v in result.items() if k not in
                      ("engineering_QC","independent_source_pixel_QC")},indent=2))
