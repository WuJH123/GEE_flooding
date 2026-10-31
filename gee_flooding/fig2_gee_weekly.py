"""One bounded GEE weekly table export for IMERG + ERA5-Land GF10 grid-days.

The 7-day maximum reduces one-task-per-day overhead without constructing a
global raster reprojection. Offline dry run by default. No cloud tasks without
explicit --submit; this is a validated pilot/export building block, not an
unattended global scheduler.
"""
from __future__ import annotations
import argparse
import json
from datetime import date,timedelta
from pathlib import Path
from .fig2_gee import selected_grid,rectangles,_weather_image,WEATHER


def plan(start,days,count,first=0):
    first_date=date.fromisoformat(start)
    if first_date<date(2021,1,1) or first_date>date(2025,12,31):
        raise ValueError("Publication study date must be within 2021-2025")
    if not 1<=days<=7 or first_date+timedelta(days=days-1)>date(2025,12,31):
        raise ValueError("One weather task supports 1-7 UTC dates within 2021-2025")
    if first<0 or not 1<=count<=30:
        raise ValueError("Bound a weekly weather task to 30 GF10 cells")
    return dict(first_date=first_date,days=days,start_row=first,count=count,
                end_date=first_date+timedelta(days=days-1),
                n_expected_grid_days=days*count,
                description=f"f2_weather_week_{first_date:%Y%m%d}_{days:02d}_{first:06d}_{first+count-1:06d}")


def launch(grid,start,days,start_row,count,folder="GEE_flooding_Figure2",
           project=None,submit=False):
    config=plan(start,days,count,start_row)
    df=selected_grid(grid,start_row,count)
    from .fig2_gee import wgs84_ring
    for r in df.itertuples(index=False):
        wgs84_ring(r.grid_x,r.grid_y)
    output={**{k:str(v) if isinstance(v,date) else v for k,v in config.items()},
            "target":"Google Drive/"+folder,
            "grid_crs":"EPSG:6933 unchanged",
            "gee_geometry_crs":"EPSG:4326",
            "task_submitted":False,
            "mode":"weather_week",
            "warning":"A plan is not completed/usable weather. Do not loop automatically."}
    if not submit:
        return output
    try:
        import ee
        ee.Initialize(project=project) if project else ee.Initialize()
    except Exception as exc:
        raise RuntimeError("Authentication/project missing for GEE") from exc
    regions=rectangles(ee,df)
    base=ee.Date(start)

    def daily_reduce(index):
        day=base.advance(ee.Number(index),"day")
        image=_weather_image(ee,day)
        fc=image.reduceRegions(collection=regions,reducer=ee.Reducer.mean(),
                               scale=10000,crs="EPSG:4326",tileScale=8)
        return fc.map(lambda ft:ee.Feature(ft).set("date",day.format("YYYY-MM-dd")))
    # Flatten one week of server-side collections without downloading pixels.
    payload=ee.FeatureCollection(
        ee.List.sequence(0,days-1).map(daily_reduce)).flatten()
    desc=config["description"]
    task=ee.batch.Export.table.toDrive(collection=payload,description=desc,
                                       folder=folder,fileNamePrefix=desc,fileFormat="CSV",
                                       selectors=["grid_id","date"]+WEATHER)
    task.start()
    output.update(task_submitted=True,task_id=task.id,
                  warning="SUBMITTED, not completed: verify Drive CSV and complete 48/336 IMERG bins")
    return output


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--start",required=True,help="First UTC date YYYY-MM-DD")
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--start-row",type=int,default=0)
    p.add_argument("--count",type=int,default=20)
    p.add_argument("--project")
    p.add_argument("--folder",default="GEE_flooding_Figure2")
    p.add_argument("--submit",action="store_true")
    a=p.parse_args(argv)
    print(json.dumps(launch(a.grid,a.start,a.days,a.start_row,a.count,
                            a.folder,a.project,a.submit),indent=2,ensure_ascii=False))


if __name__=="__main__":main()
