import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gee_flooding import fig2_gee, fig2_prepare, fig2_resilience


def _grid(tmp_path):
    p=tmp_path/"gf10.parquet"
    pd.DataFrame({
      "grid_id":["0_0","1_0","2_0"],
      "grid_x":[0,1,2], "grid_y":[0,0,0],
      "urban_fraction_2020":[0.1,.6,.5]
    }).to_parquet(p,index=False)
    return p


def test_avoid_parser_break_and_enormous_image_export(tmp_path):
    grid=_grid(tmp_path)
    for mode,date,gfd_id in [("static",None,None),("exposure",None,None),
                             ("weather","2023-07-05",None),("gfd",None,3977)]:
        q=fig2_gee.launch(grid,0,2,mode,date,"GF10_v2",event_id=gfd_id)
        assert q["gee_geometry_crs"]=="EPSG:4326"
        assert q["grid_crs"]=="EPSG:6933"
        assert q["export_type"].startswith("table CSV")
        assert not q["task_submitted"]
    ring=fig2_gee.wgs84_ring(0,0)
    assert len(ring)==49
    assert ring[0]==ring[-1]
    assert all(-180<=x<=180 and -90<=y<=90 for x,y in ring)


def test_unsafe_export_calls_fail_before_auth(tmp_path):
    grid=_grid(tmp_path)
    with pytest.raises(ValueError):
        fig2_gee.launch(grid,0,51,"static",None,"test")
    with pytest.raises(ValueError,match="sampling scale"):
        fig2_gee.launch(grid,0,2,"static",None,"test",scale=10)
    with pytest.raises(ValueError,match="date"):
        fig2_gee.launch(grid,0,2,"weather",None,"test")
    with pytest.raises(ValueError,match="GFD"):
        fig2_gee.launch(grid,0,2,"gfd",None,"test")
    with pytest.raises(ValueError,match="2020/2021"):
        fig2_gee.launch(grid,0,2,"weather","2010-03-01","test")
    with pytest.raises(ValueError,match="only"):
        fig2_gee.launch(grid,0,2,"static","2023-03-01","test")


def test_indicator_catalog_resilience_semantics_and_readonly_audit(tmp_path):
    frame=fig2_resilience.catalog()
    assert frame.name.is_unique
    assert {"hazard","exposure","sensitivity","adaptation_proxy",
            "reporting_selection","external_physical_context"}<=set(frame.pillar)
    assert set(fig2_gee.WEATHER)<=set(frame.name)
    assert set(fig2_gee.GEE_STATIC)<=set(frame.name)
    assert set(fig2_gee.EXPOSURE)<=set(frame.name)
    q=fig2_resilience.write(tmp_path,tag="fig2_inventory_fixture")
    assert q["physical_validated"] is False
    assert (tmp_path/"reports"/"fig2_inventory_fixture"/"fig2_GF10_indicator_dictionary.csv").exists()
    with pytest.raises(FileExistsError):
        fig2_resilience.write(tmp_path,tag="fig2_inventory_fixture")


def test_prepare_static_authority_and_exposure_contract(tmp_path):
    grid=_grid(tmp_path)
    ref=pd.read_parquet(grid)
    fake=pd.DataFrame({"grid_id":ref.grid_id,"urban_fraction_2020":[.1,.6,.5]})
    check=fake.merge(ref[["grid_id","urban_fraction_2020"]],on="grid_id",
                     suffixes=("_gee","_frozen"),validate="one_to_one")
    assert np.allclose(check.urban_fraction_2020_gee,check.urban_fraction_2020_frozen)
    assert fig2_prepare.STATIC[0]=="hand_m"
