import json
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from gee_flooding import fig2_local_first as triage
from gee_flooding import fig2_local_exact as exact
from gee_flooding import fig2_indicators as combine


def raster(path,values):
    with rasterio.open(path,"w",driver="GTiff",width=values.shape[1],
         height=values.shape[0],count=1,dtype=str(values.dtype),
         crs="EPSG:6933",transform=from_origin(0,10000,100,100),
         nodata=-9999) as d:
        d.write(values,1)
    return path


def gf10(tmp_path):
    g=tmp_path/"GF10.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],
                  "grid_y":[0,0],"urban_fraction_2020":[.3,.7]}).to_parquet(g,index=False)
    return g


def test_local_inventory_without_io_global(tmp_path):
    t=raster(tmp_path/"GHS_BUILT_S_E2020.tif",np.ones((100,200),dtype="float32"))
    index=tmp_path/"dataset_inventory_20261031.csv"
    pd.DataFrame({"full_path":[str(t),str(tmp_path/"CN_Floods_2020.zip")]}).to_csv(index,index=False)
    q=triage.triage(index,tmp_path,tag="fig2_triage_test")
    assert q["source_raster_values_read"] is False
    assert q["local_files_modified"]==0
    assert q["matched_candidates"]>=1
    candidates=pd.read_csv(tmp_path/"reports"/"fig2_triage_test"/"fig2_local_candidates.csv")
    assert "ghsl_built_s_2020" in set(candidates.family)
    assert candidates.loc[candidates.family.eq("ghsl_built_s_2020"),"crs"].str.contains("6933").all()
    with pytest.raises(FileExistsError):
        triage.triage(index,tmp_path,tag="fig2_triage_test")


def test_manifest_rejects_wrong_units_and_archive(tmp_path):
    path=tmp_path/"BUILT_S.tif"
    path.touch()
    good={"name":"built_fraction_2020","dataset":"GHSL_BUILT_S_R2023A",
          "epoch":"2020","kind":"cell_sum","native_units":"m2_per_native_pixel",
          "paths":[str(path)]}
    exact.validate_variable(good)
    with pytest.raises(ValueError,match="must be source m2"):
        exact.validate_variable({**good,"native_units":"percentage"})
    with pytest.raises(ValueError,match="archiv"):
        exact.validate_variable({**good,"paths":[str(tmp_path/"A.zip")]})
    with pytest.raises(ValueError,match="class codes"):
        exact.validate_variable({"name":"tree_fraction","dataset":"ESA_WORLDCOVER_V200",
                 "epoch":"2021","kind":"class_fraction","classes":[1],
                 "paths":[str(path)]})


def test_tile_combine_missing_and_overlapping_10km_cells():
    grids=pd.DataFrame({"grid_id":["0_0","1_0"]})
    good={"data":pd.DataFrame({"grid_id":["0_0","1_0"],
                        "count":[10000.,5000.],
                        "sum":[50e6,25e6],"mean":[5000.,5000.]}),
          "pixel_area":10000}
    out=exact.combine_contributions([good],grids,"built_fraction_2020","cell_sum")
    assert out.loc[0,"built_fraction_2020"]==pytest.approx(.5)
    assert pd.isna(out.loc[1,"built_fraction_2020"])
    assert out.loc[1,"coverage_built_fraction_2020"]==pytest.approx(.5)
    with pytest.raises(ValueError,match="overlapping"):
        exact.combine_contributions([good,good],grids,"built_fraction_2020","cell_sum")


def test_local_first_reconciles_and_refuses_same_source_conflicts(tmp_path):
    g=gf10(tmp_path)
    folder=tmp_path/"data"/"derived"/"fig2_local_test"
    folder.mkdir(parents=True)
    local=folder/"fig2_local_GF10_indicators.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "built_fraction_2020":[.5,np.nan],
                  "hand_m":[3.,4.]}).to_parquet(local,index=False)
    (folder/"fig2_local_exact_qc.json").write_text(json.dumps({
        "method":"exactextract_native_pixel_fraction_weighted",
        "grid_crs":"EPSG:6933"}))
    gee=tmp_path/"static"
    gee.mkdir()
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "built_fraction_2020":[.9,.7],
                  "vegetation_fraction":[.2,.6]}).to_csv(gee/"f2_static_2021_000000_000001.csv",index=False)
    qc=combine.assemble(tmp_path,g,"fig2_merged_fixture",local=local,gee_static=gee)
    assert qc["n_conflicts"]==1
    out=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_merged_fixture"/"fig2_GF10_resilience_indicators.parquet")
    assert out.loc[out.grid_id.eq("0_0"),"built_fraction_2020"].iloc[0]==pytest.approx(.5)
    assert out.loc[out.grid_id.eq("1_0"),"built_fraction_2020"].iloc[0]==pytest.approx(.7)
    assert qc["publication_ready"] is False
    assert (tmp_path/"data"/"derived"/"fig2_merged_fixture"/"fig2_gee_missing_indicator_plan.csv").exists()
    with pytest.raises(FileExistsError):
        combine.assemble(tmp_path,g,"fig2_merged_fixture",local=local,gee_static=gee)


def test_true_native_pixel_exact_ghsl_area(tmp_path):
    pytest.importorskip("exactextract")
    g=gf10(tmp_path)
    arr=np.concatenate([np.full((100,100),5000,dtype="float32"),
                        np.full((100,100),2000,dtype="float32")],axis=1)
    path=raster(tmp_path/"GHS_BUILT_S_E2020.tif",arr)
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"variables":[
        {"name":"built_fraction_2020","dataset":"GHSL_BUILT_S_R2023A",
         "epoch":"2020","kind":"cell_sum","native_units":"m2_per_native_pixel",
         "paths":[str(path)],"band":1},
        {"name":"built_area_km2_2020","dataset":"GHSL_BUILT_S_R2023A",
         "epoch":"2020","kind":"cell_sum","native_units":"m2_per_native_pixel",
         "paths":[str(path)],"band":1},
    ]}),encoding="utf-8")
    qc=exact.extract(tmp_path,g,manifest,tag="fig2_exact_fixture",count=2)
    out=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_exact_fixture"/"fig2_local_GF10_indicators.parquet")
    assert qc["grid_cell_count"]==2
    assert out.built_fraction_2020.tolist()==pytest.approx([.5,.2],rel=.0001)
    assert out.built_area_km2_2020.tolist()==pytest.approx([50,20],rel=.0001)
    assert out.coverage_built_fraction_2020.min()>0.999


def test_categorical_pixel_fractions_use_original_class_values(tmp_path):
    pytest.importorskip("exactextract")
    g=gf10(tmp_path)
    vals=np.full((100,200),80,dtype="int16")
    vals[:,:50]=10  # one quarter tree, remainder water, in first GF10
    path=raster(tmp_path/"WorldCover_2021_v200.tif",vals)
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"variables":[
       {"name":"tree_fraction","dataset":"ESA_WORLDCOVER_V200",
        "epoch":"2021","kind":"class_fraction","classes":[10],
        "paths":[str(path)]}
    ]}),encoding="utf-8")
    exact.extract(tmp_path,g,manifest,tag="fig2_cover_fixture",count=2)
    df=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_cover_fixture"/"fig2_local_GF10_indicators.parquet")
    assert df.tree_fraction.tolist()==pytest.approx([.5,0.0],abs=.001)

def test_only_missing_indicator_cells_are_targeted_for_gee(tmp_path):
    from gee_flooding import fig2_gap_grid
    grid=gf10(tmp_path)
    t=tmp_path/"integrated.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"hand_m":[1.5,np.nan]}).to_parquet(t,index=False)
    q=fig2_gap_grid.make(tmp_path,grid,t,"hand_m","fig2_missing_hand_fixture")
    assert q["missing_GF10_count"]==1
    out=pd.read_parquet(tmp_path/"data"/"reference"/"fig2_missing_hand_fixture"/"fig2_GF10_missing_grid.parquet")
    assert out.grid_id.tolist()==["1_0"]
    with pytest.raises(ValueError,match="Only GEE"):
        fig2_gap_grid.make(tmp_path,grid,t,"groundsource_count","fig2_nope")


def test_only_requested_gee_bands_and_mismatched_duplicate_rows(tmp_path):
    from gee_flooding import fig2_gee
    g=gf10(tmp_path)
    x=fig2_gee.launch(g,0,2,"static",None,"Figure2",bands="hand_m,slope_deg")
    assert x["requested_bands"]==["hand_m","slope_deg"]
    assert "_b" in x["description"] and not x["task_submitted"]
    with pytest.raises(ValueError,match="Invalid or duplicate"):
        fig2_gee.launch(g,0,2,"static",None,"Figure2",bands="hand_m,hand_m")
    with pytest.raises(ValueError,match="only supports"):
        fig2_gee.launch(g,0,2,"weather","2024-07-01","Figure2",bands="hand_m")
    folder=tmp_path/"gee"
    folder.mkdir()
    pd.DataFrame({"grid_id":["0_0","1_0"],"hand_m":[2.,3.]}).to_csv(
        folder/"f2_static_2021_000000_000001_baaa.csv",index=False)
    pd.DataFrame({"grid_id":["0_0","1_0"],"slope_deg":[.5,.8]}).to_csv(
        folder/"f2_static_2021_000000_000001_bbbb.csv",index=False)
    merged=combine._load_gee(folder,"f2_static_")
    assert {"hand_m","slope_deg"}<=set(merged)
    assert len(merged)==2
    pd.DataFrame({"grid_id":["0_0"],"hand_m":[10.]}).to_csv(
        folder/"f2_static_2021_000000_000000_bccc.csv",index=False)
    with pytest.raises(ValueError,match="Conflicting"):
        combine._load_gee(folder,"f2_static_")


def test_shapely_fallback_equal_area_matches_exactextract(tmp_path):
    from gee_flooding import fig2_local_exact as exact
    g=gf10(tmp_path)
    a=np.concatenate([np.full((100,100),5000,dtype="float32"),
                      np.full((100,100),2000,dtype="float32")],axis=1)
    p=raster(tmp_path/"GHS_BUILT_S_2020.tif",a)
    spec=tmp_path/"sources.json"
    spec.write_text(json.dumps({"variables":[{
        "name":"built_fraction_2020","dataset":"GHSL_BUILT_S_R2023A",
        "epoch":"2020","kind":"cell_sum","native_units":"m2_per_native_pixel",
        "paths":[str(p)]}]}),encoding="utf-8")
    qc=exact.extract(tmp_path,g,spec,tag="fig2_shapely_qa",count=2,
                     backend="shapely")
    assert qc["method"]=="shapely_native_pixel_fraction_weighted"
    df=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_shapely_qa"/"fig2_local_GF10_indicators.parquet")
    assert df.built_fraction_2020.tolist()==pytest.approx([.5,.2],abs=.0001)
    assert df.coverage_built_fraction_2020.min()>.999
    # same frozen input, independent exactextract implementation
    other=exact.extract(tmp_path,g,spec,tag="fig2_cpp_qa",count=2,
                        backend="exactextract")
    d2=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_cpp_qa"/"fig2_local_GF10_indicators.parquet")
    assert df.built_fraction_2020.tolist()==pytest.approx(
        d2.built_fraction_2020.tolist(),abs=.0001)


def test_missing_GEE_task_planner_respects_original_ids_and_source_groups(tmp_path):
    from gee_flooding import fig2_backfill_plan
    g=gf10(tmp_path)
    p=tmp_path/"merged.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "built_fraction_2020":[.5,np.nan],
                  "hand_m":[np.nan,np.nan],
                  "population_count_2020":[np.nan,np.nan]}).to_parquet(p,index=False)
    qc=fig2_backfill_plan.plan(tmp_path,g,p,tag="fig2_missing_task_fixture",
                              max_cells=1)
    assert qc["n_planned_jobs"]>=3
    assert qc["remote_submissions"]==0
    out=tmp_path/"data"/"reference"/"fig2_missing_task_fixture"
    tasks=pd.read_csv(out/"fig2_gee_backfill_tasks.csv")
    assert tasks.n_grid.max()==1
    assert set(tasks.source_family)=={"merit","landcover","builtform","population"}
    assert tasks.loc[tasks.bands.eq("built_fraction_2020"),"n_grid"].sum()==1
    for row in tasks.itertuples(index=False):
        src=pd.read_parquet(out/row.grid_file)
        assert len(src)==row.n_grid
        assert set(src.grid_id)<=set(pd.read_parquet(g).grid_id)
    with pytest.raises(FileExistsError):
        fig2_backfill_plan.plan(tmp_path,g,p,tag="fig2_missing_task_fixture")
