"""GEE Figure2 *bounded* export launcher. Source assets are public; no tasks on import.

Each weather task covers every selected GF10 urban cell for ONE UTC day.
Run with --submit explicitly. Reassemble and audit complete coverage locally.
Do not confuse GEE queued/running tasks with successfully downloaded data.
"""
from __future__ import annotations
import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PRODUCTS = {
    "imerg": "NASA/GPM_L3/IMERG_V07",
    "merit": "MERIT/Hydro/v1_0_1",
    "worldcover": "ESA/WorldCover/v200",
    "ghsl_2000": "JRC/GHSL/P2023A/GHS_BUILT_S/2000",
    "ghsl_2020": "JRC/GHSL/P2023A/GHS_BUILT_S/2020",
}


def selected_grid(grid_path, start_row=0, count=50):
    if start_row < 0 or not (1 <= count <= 250):
        raise ValueError("0 <= start-row and 1 <= count <= 250 required")
    required = ["grid_id", "grid_x", "grid_y"]
    grid = pd.read_parquet(grid_path, columns=required)
    if grid.grid_id.duplicated().any():
        raise ValueError("Duplicate frozen GF10 cell")
    if any(str(z) != f"{int(x)}_{int(y)}" for z,x,y in zip(grid.grid_id,grid.grid_x,grid.grid_y)):
        raise ValueError("Grid ID != EPSG:6933 10km indices")
    grid = grid.sort_values("grid_id").iloc[start_row:start_row+count]
    if grid.empty:
        raise ValueError("Row selection empty")
    return grid


def rectangles(ee, grid):
    features = []
    for r in grid.itertuples(index=False):
        x,y=int(r.grid_x)*10000,int(r.grid_y)*10000
        geo = ee.Geometry.Rectangle([x,y,x+10000,y+10000], proj="EPSG:6933", geodesic=False)
        features.append(ee.Feature(geo, {"grid_id":str(r.grid_id)}))
    return ee.FeatureCollection(features)


def _static_image(ee):
    h=ee.Image(PRODUCTS["merit"])
    gh20=ee.Image(PRODUCTS["ghsl_2020"]).select("built_surface").divide(10000).clamp(0,1)
    gh00=ee.Image(PRODUCTS["ghsl_2000"]).select("built_surface").divide(10000).clamp(0,1)
    lc=ee.ImageCollection(PRODUCTS["worldcover"]).first().select("Map")
    vegetation=lc.remap([10,20,30,40,50,60,70,80,90,95,100],
                        [1,1,1,1,0,0,0,0,1,1,0], 0).rename("vegetation_fraction")
    # Reduce 10m classes to 100m area-weighted share before GF10 aggregation.
    vegetation=vegetation.reduceResolution(reducer=ee.Reducer.mean(),maxPixels=1024)
    neighborhood=gh20.focal_mean(radius=1500,units="meters")
    fragmentation=gh20.focal_std(radius=1000,units="meters")
    return ee.Image.cat([
        h.select("hnd").rename("hand_m"),
        ee.Terrain.slope(h.select("elv")).rename("slope_deg"),
        gh20.rename("built_fraction_2020"),
        neighborhood.rename("built_neighbor_density"),
        fragmentation.rename("built_fragmentation"),
        gh20.subtract(gh00).rename("built_growth_2000_2020"),
        vegetation
    ])


def _weather_image(ee, day):
    base=ee.Date(day)
    rain=ee.ImageCollection(PRODUCTS["imerg"]).select("precipitation")
    daily=rain.filterDate(base,base.advance(1,"day"))
    before=rain.filterDate(base.advance(-7,"day"),base)
    # Half-hour precipitation is a rate (mm/h), NOT depth; integrate using 0.5 h.
    p24=daily.sum().multiply(.5).rename("rain_24h_mm")
    api=before.sum().multiply(.5).rename("api_7d_mm")
    roll=[]
    for half_hour in range(43):
        t=base.advance(half_hour*30,"minute")
        roll.append(rain.filterDate(t,t.advance(3,"hour")).sum().multiply(.5))
    p3=ee.ImageCollection.fromImages(roll).max().rename("rain_3h_mm")
    return ee.Image.cat([p24,p3,api,
                         daily.count().rename("n_obs_24h"),
                         before.count().rename("n_obs_7d")])


def launch(grid, start_row, count, mode, day, folder, submit=False):
    frame=selected_grid(grid,start_row,count)
    batch=f"{start_row:06d}_{start_row+len(frame)-1:06d}"
    if mode=="weather" and not day:
        raise ValueError("Weather export needs --date in UTC")
    if day:
        date.fromisoformat(day)
    label=(f"f2_weather_{day.replace('-','')}_{batch}" if mode=="weather"
           else f"f2_static_2021_{batch}")
    summary={"description":label,"mode":mode,"rows":len(frame),"task_submitted":False,
             "grid_first":str(frame.iloc[0].grid_id),"grid_last":str(frame.iloc[-1].grid_id),
             "export_destination":"Google Drive / "+folder,
             "warning":"Dry run. Successful GEE tasks and downloaded CSVs require external audit."}
    if not submit:
        return summary
    try:
        import ee
        ee.Initialize()
    except Exception as exc:
        raise RuntimeError("Earth Engine unavailable; run earthengine authenticate and configure a project") from exc
    region=rectangles(ee,frame)
    image=_weather_image(ee,day) if mode=="weather" else _static_image(ee)
    # Explicit equal-area 100m aggregation; never request 10m global reduceRegions.
    reduced=image.reduceRegions(collection=region,reducer=ee.Reducer.mean(),
                                scale=100,crs="EPSG:6933",tileScale=8)
    task=ee.batch.Export.table.toDrive(collection=reduced,description=label,
                                      folder=folder,fileNamePrefix=label,fileFormat="CSV",
                                      selectors=(["grid_id","rain_24h_mm","rain_3h_mm",
                                                  "api_7d_mm","n_obs_24h","n_obs_7d"]
                                                 if mode=="weather" else
                                                 ["grid_id","hand_m","slope_deg",
                                                  "built_fraction_2020","built_neighbor_density",
                                                  "built_fragmentation","built_growth_2000_2020",
                                                  "vegetation_fraction"]))
    task.start()
    summary.update(task_submitted=True,task_id=task.id,
                   "important":"Download the matching Drive CSV. Do not treat READY as completed.")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--start-row",type=int,default=0)
    p.add_argument("--count",type=int,default=50)
    p.add_argument("--mode",choices=["static","weather"],required=True)
    p.add_argument("--date",help="UTC YYYY-MM-DD; mandatory for weather")
    p.add_argument("--folder",default="GEE_flooding_Figure2")
    p.add_argument("--submit",action="store_true",help="Actually submit one GEE export task")
    a=p.parse_args()
    import json
    print(json.dumps(launch(a.grid,a.start_row,a.count,a.mode,a.date,a.folder,a.submit),
                     indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
