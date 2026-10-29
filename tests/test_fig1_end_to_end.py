"""Smoke test of actual Figure1 orchestration with only synthetic geocodes."""
import json
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import box
from pyproj import Transformer
from gee_flooding.fig1 import build,UCDB_LAYER

def test_complete_figure1_synthetic_pipeline(tmp_path):
    data=tmp_path/"input"
    data.mkdir()
    cells=pd.DataFrame({"grid_id":["1_2","2_2","3_2"],
                        "grid_x":[1,2,3],"grid_y":[2,2,2]})
    lon,lat=Transformer.from_crs(6933,4326,always_xy=True).transform(
        [15000,25000,35000],[25000]*3)
    cells["longitude"]=lon;cells["latitude"]=lat
    grid=data/"grid.parquet";cells.to_parquet(grid,index=False)
    labels=pd.DataFrame([
        ("aa","1_2","2021-02-01","HIGH_GEOCODE_SPECIFICITY"),
        ("bb","1_2","2022-02-01","HIGH_GEOCODE_SPECIFICITY"),
        ("cc","2_2","2023-02-01","HIGH_GEOCODE_SPECIFICITY"),
    ],columns=["event_id","grid_id","date","geocode_quality"])
    label_path=data/"label.parquet";labels.to_parquet(label_path,index=False)
    qc={"status":"PASS_LABEL_GEOCODE_AUDIT","rows_processed":4,
        "count_by_status":{"MATCHED":3,"NOT_IN_GF10_URBAN_DOMAIN":1},
        "count_by_quality":{"HIGH_GEOCODE_SPECIFICITY":3,
                            "MEDIUM_GEOCODE_SPECIFICITY":0,
                            "LOW_GEOCODE_SPECIFICITY":0,"NOT_ELIGIBLE":1}}
    qcpath=data/"qc.json";qcpath.write_text(json.dumps(qc),encoding="utf-8")
    ucdb=data/"ucdb.gpkg"
    cities=gpd.GeoDataFrame({"ID_UC_G0":["A","B"]},
        geometry=[box(10000,20000,30000,30000),box(30000,20000,40000,30000)],
        crs="EPSG:6933")
    cities.to_file(ucdb,layer=UCDB_LAYER,driver="GPKG",engine="pyogrio")
    world=data/"world.geojson"
    gpd.GeoDataFrame({"ADMIN":["Testland"],"CONTINENT":["Testcontinent"]},
        geometry=[box(-10,-10,10,10)],crs="EPSG:4326").to_file(world,driver="GeoJSON")
    gfid=data/"gfid.xlsx"
    pd.DataFrame({"Source":["DFO"],"Start Date":[pd.Timestamp("2021-02-01")],
                  "End Date":[pd.Timestamp("2021-02-02")],"Lat":[lat[0]],"Lon":[lon[0]]}
                 ).to_excel(gfid,sheet_name="Aggregated",index=False)
    result=build(tmp_path,grid,label_path,qcpath,ucdb,tag="fig1_test",
                 world=world,gfid=gfid,city_min_reports=1,city_min_years=1)
    assert result["raw_groundsource_rows"]==4
    assert result["mapped_geocoded_reports"]==3
    assert result["high_distinct_grid_days"]==3
    assert result["eligible_cities"]==2
    assert result["gfid_candidate_grid_days_by_source_family"].get("DFO")==1
    output=tmp_path/"outputs/fig1_test"
    for name in ("Figure1_GEE_observation.png","Figure1_GEE_observation.pdf",
                 "fig1_qc_and_provenance.json","fig1_ucdb_city_sample_audit.csv",
                 "fig1_gfid_candidate_concordance.parquet"):
        assert (output/name).is_file(),name
