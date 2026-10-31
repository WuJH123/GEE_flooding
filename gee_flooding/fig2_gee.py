"""GF10-safe Earth Engine table exports for Figure 2.

Default is a *no-network* dry run. Only --submit starts ONE bounded table task.
No global Image.toDrive exports. Never use EPSG:6933 inside Earth Engine:
the frozen 10km EPSG:6933 grid is converted locally to densified EPSG:4326
polygons and its stable grid_id accompanies each exported record.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
import pandas as pd

MAX_ROWS = 50
PRODUCTS = {
    "imerg": "NASA/GPM_L3/IMERG_V07",
    "era5land": "ECMWF/ERA5_LAND/HOURLY",
    "merit": "MERIT/Hydro/v1_0_1",
    "worldcover": "ESA/WorldCover/v200",
    "ghsl_2000": "JRC/GHSL/P2023A/GHS_BUILT_S/2000",
    "ghsl_2020": "JRC/GHSL/P2023A/GHS_BUILT_S/2020",
    "ghsl_pop_2020": "JRC/GHSL/P2023A/GHS_POP/2020",
    "gfd": "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1",
}
STATIC = [
    "hand_m", "elevation_m", "slope_deg", "upstream_area_km2",
    "river_water_fraction", "urban_fraction_2020", "vegetation_fraction",
    "tree_fraction", "grass_fraction", "cropland_fraction",
    "wetland_fraction", "water_fraction", "bare_fraction",
    "built_fraction_2020", "built_nres_fraction_2020",
    "built_neighbor_density", "built_fragmentation",
    "built_growth_2000_2020",
]
# urban_fraction_2020 is supplied by the frozen grid, NOT Earth Engine.
GEE_STATIC = [x for x in STATIC if x != "urban_fraction_2020"]
WEATHER = ["rain_24h_mm", "rain_3h_mm", "api_7d_mm",
           "n_obs_24h", "n_obs_7d", "soil_water_0_7cm",
           "soil_water_7_28cm", "temperature_2m_c"]
EXPOSURE = ["population_count_2020", "built_area_km2_2020",
            "built_nres_area_km2_2020"]
GFD = ["flood_fraction_observable", "observable_fraction", "clear_views_mean"]


def selected_grid(grid_path, start_row=0, count=20):
    if start_row < 0 or not 1 <= count <= MAX_ROWS:
        raise ValueError(f"Expected start-row>=0 and 1<=count<={MAX_ROWS} for bounded GEE task")
    d = pd.read_parquet(grid_path, columns=["grid_id", "grid_x", "grid_y", "urban_fraction_2020"])
    if d.grid_id.duplicated().any():
        raise ValueError("Frozen grid contains duplicate IDs")
    if any(str(g) != f"{int(x)}_{int(y)}" for g, x, y in
           zip(d.grid_id, d.grid_x, d.grid_y)):
        raise ValueError("GF10 id/x/y alignment mismatch")
    d = d.sort_values("grid_id").iloc[start_row:start_row + count].copy()
    if len(d) != count:
        raise ValueError("Selection exceeds frozen GF10 grid")
    return d


def wgs84_ring(x, y, transformer=None, steps=12):
    """Densify source 10km edges in EPSG:6933 before conversion; never alter ID."""
    if transformer is None:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
    x0, y0 = int(x)*10000, int(y)*10000
    corners = [(x0,y0), (x0+10000,y0), (x0+10000,y0+10000),
               (x0,y0+10000), (x0,y0)]
    pts = []
    for a, b in zip(corners[:-1], corners[1:]):
        for i in range(steps):
            t = i / steps
            pts.append((a[0] + t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
    pts.append(corners[0])
    lon, lat = transformer.transform([p[0] for p in pts],[p[1] for p in pts])
    if not all(-180 <= u <= 180 and -90 <= v <= 90 for u,v in zip(lon,lat)):
        raise ValueError("GF10 cell outside WGS84 bounds")
    if max(lon) - min(lon) > 180:
        raise ValueError("Antimeridian cell requires explicit split; cannot create world-spanning polygon")
    return [[float(u),float(v)] for u,v in zip(lon,lat)]


def rectangles(ee, grid):
    from pyproj import Transformer
    transformer=Transformer.from_crs(6933,4326,always_xy=True)
    features=[]
    for r in grid.itertuples(index=False):
        ring=wgs84_ring(r.grid_x,r.grid_y,transformer)
        geom=ee.Geometry.Polygon([ring],proj="EPSG:4326",geodesic=False)
        features.append(ee.Feature(geom,{"grid_id":str(r.grid_id),
                                        "urban_fraction_2020":float(r.urban_fraction_2020)}))
    return ee.FeatureCollection(features)


def _static_image(ee):
    h=ee.Image(PRODUCTS["merit"])
    gh20=ee.Image(PRODUCTS["ghsl_2020"])
    gh00=ee.Image(PRODUCTS["ghsl_2000"])
    b20=gh20.select("built_surface").divide(10000).clamp(0,1)
    b00=gh00.select("built_surface").divide(10000).clamp(0,1)
    nres=gh20.select("built_surface_nres").divide(10000).clamp(0,1)
    lc=ee.ImageCollection(PRODUCTS["worldcover"]).first().select("Map")
    # WorldCover 10m -> coarse regional means via area-weighted aggregation,
    # not nearest-neighbour sampling of categorical classes.
    def share(classes, name):
        flag=lc.remap(classes,[1]*len(classes),0).rename(name)
        return flag.reduceResolution(reducer=ee.Reducer.mean(),maxPixels=1024)
    # Other 90/100m rasters also use mean aggregation before 200m reduction.
    def down(image):
        return image.reduceResolution(reducer=ee.Reducer.mean(),maxPixels=1024)
    return ee.Image.cat([
        down(h.select("hnd").rename("hand_m")),
        down(h.select("elv").rename("elevation_m")),
        down(ee.Terrain.slope(h.select("elv")).rename("slope_deg")),
        down(h.select("upa").rename("upstream_area_km2")),
        down(h.select("wat").eq(1).rename("river_water_fraction")),
        share([10,20,30,40,90,95],"vegetation_fraction"),
        share([10],"tree_fraction"), share([30],"grass_fraction"),
        share([40],"cropland_fraction"),share([90,95],"wetland_fraction"),
        share([80],"water_fraction"),share([60],"bare_fraction"),
        down(b20.rename("built_fraction_2020")),
        down(nres.rename("built_nres_fraction_2020")),
        down(b20.focal_mean(radius=1500,units="meters").rename("built_neighbor_density")),
        down(b20.focal_std(radius=1000,units="meters").rename("built_fragmentation")),
        down(b20.subtract(b00).rename("built_growth_2000_2020")),
    ])


def _weather_image(ee, day):
    base=ee.Date(day)
    rain=ee.ImageCollection(PRODUCTS["imerg"]).select("precipitation")
    today=rain.filterDate(base,base.advance(1,"day"))
    history=rain.filterDate(base.advance(-7,"day"),base)
    # Each image is mm/h, each timestep is half an hour.
    p24=today.sum().multiply(.5).rename("rain_24h_mm")
    p7=history.sum().multiply(.5).rename("api_7d_mm")
    windows=[rain.filterDate(base.advance(i*30,"minute"),
                 base.advance(i*30+180,"minute")).sum().multiply(.5)
             for i in range(43)]
    p3=ee.ImageCollection.fromImages(windows).max().rename("rain_3h_mm")
    # Antecedent values only; no future soil-moisture leakage.
    era=ee.ImageCollection(PRODUCTS["era5land"]).filterDate(base.advance(-24,"hour"),base)
    sw1=era.select("volumetric_soil_water_layer_1").mean().rename("soil_water_0_7cm")
    sw2=era.select("volumetric_soil_water_layer_2").mean().rename("soil_water_7_28cm")
    temp=era.select("temperature_2m").mean().subtract(273.15).rename("temperature_2m_c")
    return ee.Image.cat([p24,p3,p7,today.count().rename("n_obs_24h"),
                         history.count().rename("n_obs_7d"),sw1,sw2,temp])


def _exposure_image(ee):
    # GHSL's counts and built m2 refer to an original 100m (=10000m2)
    # equal-area grid cell. First form density/fraction, then re-integrate
    # using output pixelArea after sampling in EPSG:4326. Summing raw source
    # cell counts on a geographic output grid is NOT population-conserving.
    area=ee.Image.pixelArea()
    b=ee.Image(PRODUCTS["ghsl_2020"])
    pop=ee.Image(PRODUCTS["ghsl_pop_2020"]).select("population_count")
    return ee.Image.cat([
        pop.divide(10000).multiply(area).rename("population_count_2020"),
        b.select("built_surface").divide(10000).multiply(area).divide(1e6)
          .rename("built_area_km2_2020"),
        b.select("built_surface_nres").divide(10000).multiply(area).divide(1e6)
          .rename("built_nres_area_km2_2020")
    ])


def _gfd_image(ee,event_id):
    e=ee.Image(ee.ImageCollection(PRODUCTS["gfd"])
               .filter(ee.Filter.eq("id",int(event_id))).first())
    # This is satellite-observable fraction, not a confirmed-flood/no-flood label.
    clear=e.select("clear_views")
    observable=clear.gt(0).And(e.select("jrc_perm_water").neq(1))
    flooded=e.select("flooded").updateMask(observable)
    return ee.Image.cat([
        flooded.rename("flood_fraction_observable"),
        observable.unmask(0).rename("observable_fraction"),
        clear.rename("clear_views_mean")
    ])


def validate_export_contract(mode,day=None,event_id=None,scale=None):
    if mode not in ("static","weather","exposure","gfd"):
        raise ValueError("Unknown export mode")
    if mode=="weather":
        if day is None:raise ValueError("Weather export requires a UTC date")
        if date.fromisoformat(day) < date(2021,1,1):
            raise ValueError("2020/2021 static covariates are not valid for historical predictive weather")
    elif day is not None:
        raise ValueError("--date applies only to weather")
    if mode=="gfd":
        if event_id is None or int(event_id) <= 0:
            raise ValueError("GFD export needs a positive official Dartmouth flood ID")
    elif event_id is not None:
        raise ValueError("--gfd-id only applies to gfd")
    defaults={"static":200, "weather":10000,"exposure":100,"gfd":250}
    actual=defaults[mode] if scale is None else int(scale)
    ranges={"static":(150,400),"weather":(8000,12000),
            "exposure":(100,150),"gfd":(250,500)}
    if not ranges[mode][0]<=actual<=ranges[mode][1]:
        raise ValueError("Invalid sampling scale; prevents enormous native-res exports")
    return actual


def launch(grid,start_row,count,mode,day,folder,submit=False,
           event_id=None,project=None,scale=None,bands=None):
    effective_scale=validate_export_contract(mode,day,event_id,scale)
    if bands:
        if isinstance(bands,str):
            bands=[s.strip() for s in bands.split(",") if s.strip()]
        allowed={"static":GEE_STATIC,"exposure":EXPOSURE}.get(mode)
        if not allowed:
            raise ValueError("Band-selective GEE gap export only supports static/exposure")
        if not bands or len(set(bands))!=len(bands) or set(bands)-set(allowed):
            raise ValueError("Invalid or duplicate GEE band selection: "+str(bands))
    else:
        bands=None
    d=selected_grid(grid,start_row,count)
    last=start_row+len(d)-1
    batch=f"{start_row:06d}_{last:06d}"
    labels={"static":f"f2_static_2021_{batch}",
            "exposure":f"f2_exposure_2020_{batch}",
            "weather":f"f2_weather_{day.replace('-','')}_{batch}" if day else "",
            "gfd":f"f2_gfd_{int(event_id):06d}_{batch}" if event_id is not None else ""}
    description=labels[mode]
    if bands:
        # Task names remain unique for different selected indicators and cells.
        signature=",".join(sorted(bands))+"|"+",".join(d.grid_id.astype(str))
        description += "_b"+hashlib.sha256(signature.encode()).hexdigest()[:10]
    result={"description":description,"mode":mode,"rows":len(d),"task_submitted":False,
            "requested_bands":bands if bands else ("ALL_"+mode),
            "sampling_scale_m":effective_scale,"grid_crs":"EPSG:6933",
            "gee_geometry_crs":"EPSG:4326",
            "export_type":"table CSV, one row per frozen 10km GF10 cell",
            "grid_first":str(d.iloc[0].grid_id),"grid_last":str(d.iloc[-1].grid_id),
            "target":"Google Drive/"+folder,
            "status":"DRY_RUN" if not submit else "REQUESTED",
            "scientific_note":"GFD is an external large-flood satellite observable mask, not pluvial urban ground truth" if mode=="gfd" else "No resampling creates finer physical resolution"}
    # Even dry-run validates anti-meridian and geographic boundary of each selected cell.
    for r in d.itertuples(index=False):
        wgs84_ring(r.grid_x,r.grid_y)
    if not submit:return result
    try:
        import ee
        if project:ee.Initialize(project=project)
        else:ee.Initialize()
    except Exception as e:
        raise RuntimeError("Earth Engine auth/project missing. Run earthengine authenticate; set_project") from e
    fc=rectangles(ee,d)
    if mode=="weather":
        image=_weather_image(ee,day)
        selectors=["grid_id"]+WEATHER
        reducer=ee.Reducer.mean()
    elif mode=="static":
        requested=bands or GEE_STATIC
        image=_static_image(ee).select(requested)
        selectors=["grid_id","urban_fraction_2020"]+requested
        reducer=ee.Reducer.mean()
    elif mode=="exposure":
        requested=bands or EXPOSURE
        image=_exposure_image(ee).select(requested)
        selectors=["grid_id"]+requested
        reducer=ee.Reducer.sum()
    else:
        n=ee.ImageCollection(PRODUCTS["gfd"]).filter(ee.Filter.eq("id",int(event_id))).size().getInfo()
        if n!=1:raise ValueError(f"GFD Dartmouth id {event_id} returns {n} images (required exactly one)")
        image=_gfd_image(ee,event_id)
        selectors=["grid_id"]+GFD
        reducer=ee.Reducer.mean()
    # EPSG:4326 is intentionally explicit: EPSG:6933 intermittently fails in GEE.
    # All operations are bounded tables, never large global raster export.
    reduced=image.reduceRegions(collection=fc,reducer=reducer,
                                scale=effective_scale,crs="EPSG:4326",tileScale=8)
    task=ee.batch.Export.table.toDrive(
        collection=reduced,description=description,folder=folder,
        fileNamePrefix=description,fileFormat="CSV",selectors=selectors)
    task.start()
    result.update(task_submitted=True,task_id=task.id,status="SUBMITTED_NOT_COMPLETE",
                  warning="Only completed and quality-audited downloaded CSVs can enter Figure2")
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--start-row",type=int,default=0)
    p.add_argument("--count",type=int,default=20)
    p.add_argument("--mode",choices=["static","weather","exposure","gfd"],required=True)
    p.add_argument("--date",help="YYYY-MM-DD UTC day; weather mode only")
    p.add_argument("--gfd-id",type=int,help="Official Dartmouth flood ID in GFD (2000-2018)")
    p.add_argument("--scale",type=int,default=None)
    p.add_argument("--folder",default="GEE_flooding_Figure2")
    p.add_argument("--project",help="GEE Cloud project, for submission only")
    p.add_argument("--submit",action="store_true",help="Start ONE table export")
    p.add_argument("--bands",help="Comma-separated missing indicators for static/exposure only; no new GEE datasets")
    a=p.parse_args(argv)
    out=launch(a.grid,a.start_row,a.count,a.mode,a.date,a.folder,
               a.submit,a.gfd_id,a.project,a.scale,a.bands)
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
