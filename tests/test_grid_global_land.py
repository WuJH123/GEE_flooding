"""Synthetic shoreline topology, micro-island, antimeridian and polar regression."""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from gee_flooding.grid_global_land import build, compute, _records, _split_dateline


def create_source(tmp_path):
    source=tmp_path/"GSHHS_shp"/"f"
    source.mkdir(parents=True)
    shapes={
        1:[
            box(0,0,1,1),                    # large mainland, includes lake
            box(10.001,.001,10.002,.002),    # tiny island, no 10km centroid in it
            box(-32,87,-31,88),             # land above global EPSG6933 latitude limit
            Polygon([(179.9,1),(-179.9,1),(-179.9,1.1),(179.9,1.1)]),
        ],
        2:[box(.20,.20,.45,.45)],           # lake removed
        3:[box(.25,.25,.30,.30)],           # island in lake restored
        4:[box(.26,.26,.27,.27)],           # pond on island removed
        6:[box(-35,-89,-20,-88)],           # Antarctic grounding-line proxy
    }
    for level,parts in shapes.items():
        gdf=gpd.GeoDataFrame({"level":[level]*len(parts),
                              "geometry":parts},crs="EPSG:4326")
        gdf.to_file(source/f"GSHHS_f_L{level}.shp")
    return source


def test_source_includes_small_island_and_hierarchical_holes(tmp_path):
    source=create_source(tmp_path)
    data=build(tmp_path,source,resolution="f",tag="gf10_fixture_global")
    assert data["n_GF10_land_cells"]>0
    assert data["n_by_zone"]["N"]>0
    assert data["n_by_zone"]["S"]>0
    assert data["n_by_zone"]["G"]>0
    assert max(data["per_zone_polygon_to_grid_relative_area_error"].values())<.003
    out=tmp_path/"data"/"reference"/"gf10_fixture_global"
    df=pd.read_parquet(out/"gf10_global_all_land.parquet")
    assert not df.grid_id.duplicated().any()
    assert df.grid_crs.eq("EPSG:6933").any()
    assert df.grid_crs.eq("EPSG:6931").any()
    assert df.grid_crs.eq("EPSG:6932").any()
    # island is smaller than 100m wide and its cell centre is ocean:
    tiny=df.loc[(df.longitude.between(9.9,10.2)) &
                df.latitude.between(-.2,.2)]
    assert not tiny.empty
    assert tiny.land_fraction.min()>0
    assert tiny.land_fraction.min()<.05
    # A known European/synthetic global grid ID must remain literal x_y.
    assert all(not x.startswith("G_") for x in df.loc[df.zone.eq("G"),"grid_id"])
    assert all(x.startswith("N_") for x in df.loc[df.zone.eq("N"),"grid_id"])
    assert all(x.startswith("S_") for x in df.loc[df.zone.eq("S"),"grid_id"])


def test_coastline_dateline_crossing_not_world_spanning():
    source=Polygon([(179.9,1),(-179.9,1),(-179.9,1.1),(179.9,1.1)])
    parts=list(_split_dateline(source))
    assert len(parts)>=2
    assert all(p.bounds[2]-p.bounds[0]<1 for p in parts)
    assert all(p.area>0 for p in parts)


def test_fail_closed_if_required_antarctica_level_missing(tmp_path):
    source=create_source(tmp_path)
    (source/"GSHHS_f_L6.shp").unlink()
    with pytest.raises(FileNotFoundError,match="required GSHHG"):
        compute(source,resolution="f")


def test_legacy_global_grid_id_unchanged_and_audited(tmp_path):
    source=create_source(tmp_path)
    tab,_,_,_=compute(source,"f",subset=(0,0,2,2))
    frame,_=_records(tab)
    globalids=frame.loc[frame.zone.eq("G"),["grid_id","grid_x","grid_y"]]
    old=tmp_path/"legacy.parquet"
    globalids.head(2).to_parquet(old,index=False)
    q=build(tmp_path,source,"f",legacy=old,
            tag="gf10_fixture_legacy",bounds=(0,0,2,2),
            require_legacy=False)
    assert q["legacy_urban_missing_count"]==0
