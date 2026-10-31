"""GFD MODIS independently sensed WATER pilot for a *known* DFO event ID.

Historical 2000–2018 only. This is selected-case satellite flood-water support,
NOT a globally sampled validation or a diagnosis of pluvial runoff.
"""
import pandas as pd

def gfd_probe(project,grid,grid_id,gfd_event_id,submit=False,
              description="FIG1_GFD_VERIFIED_WATER_PILOT"):
    if int(gfd_event_id)<=0:raise ValueError("Provide a published DFO/GFD positive event ID")
    from pathlib import Path
    g=pd.read_parquet(grid,columns=["grid_id","grid_x","grid_y"])
    if g.grid_id.duplicated().any():raise ValueError("Duplicate GF10")
    q=g[g.grid_id.astype(str).eq(str(grid_id))]
    if len(q)!=1:raise ValueError("GF10 grid_id not found in frozen original frame")
    r=q.iloc[0]
    info={"status":"DRY_RUN_NOT_SUBMITTED" if not submit else "CHECKING_GEE_EVENT",
          "project":project,"grid_id":str(grid_id),"gfd_id":int(gfd_event_id),
          "dataset":"GLOBAL_FLOOD_DB/MODIS_EVENTS/V1",
          "observables":["temporary_flooded_area_km2","clear_view_area_km2",
                         "valid_nonpermanent_land_area_km2"],
          "missing_or_no_detection_policy":"never call no satellite inundation a true no-flood",
          "mechanism_policy":"GFD event comes from DFO; satellite water does not prove pluvial"}
    if not submit:return info
    import ee
    ee.Initialize(project=project)
    gfd=ee.ImageCollection("GLOBAL_FLOOD_DB/MODIS_EVENTS/V1").filter(
         ee.Filter.eq("id",int(gfd_event_id)))
    if int(gfd.size().getInfo())!=1:
        raise ValueError("GFD event ID missing or not unique; check source official id")
    image=ee.Image(gfd.first())
    x,y=int(r.grid_x),int(r.grid_y)
    cell=ee.Geometry.Rectangle([x*10000,y*10000,
        (x+1)*10000,(y+1)*10000],proj="EPSG:6933",geodesic=False)
    clear=image.select("clear_views").gt(0)
    permanent=image.select("jrc_perm_water").eq(1)
    valid=clear.And(permanent.Not())
    flood=image.select("flooded").eq(1).And(valid)
    # Source physical flood classification uses MODIS 250m; conserve area
    # using the same fixed analysis geometry, no pixel-count=km2 shortcuts.
    pix=ee.Image.pixelArea()
    sat=ee.Image.cat([
      pix.updateMask(flood).rename("temporary_flooded_area_m2"),
      pix.updateMask(clear).rename("clear_view_area_m2"),
      pix.updateMask(valid).rename("valid_nonpermanent_area_m2")
    ])
    vals=sat.reduceRegion(reducer=ee.Reducer.sum(),geometry=cell,
              crs="EPSG:6933",scale=250,maxPixels=100000,
              bestEffort=False)
    features=ee.FeatureCollection([ee.Feature(cell.centroid(100),{
       "grid_id":str(grid_id),"gfd_id":int(gfd_event_id),
       "temporary_flood_km2":ee.Number(
           vals.get("temporary_flooded_area_m2",0)).divide(1e6),
       "clear_view_area_km2":ee.Number(
           vals.get("clear_view_area_m2",0)).divide(1e6),
       "valid_land_area_km2":ee.Number(
           vals.get("valid_nonpermanent_area_m2",0)).divide(1e6),
       "source_lineage":"DFO_SELECTED_GFD_SATELLITE_WATER",
       "pluvial_mechanism":"NOT_CONFIRMED",
       "not_detected_is_not_no_flood":True
    })])
    task=ee.batch.Export.table.toDrive(collection=features,
        description=description,folder="GEE_flooding_fig1_validation",
        fileFormat="CSV")
    task.start()
    info["status"]="SUBMITTED_REQUIRES_SUCCESS_CSV_AND_MANUAL_SENSOR_QA"
    info["task_id"]=task.id
    return info
