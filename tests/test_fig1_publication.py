"""Synthetic contract tests only. No local E-drive reads or network."""
import json
import numpy as np
import pandas as pd
import pytest

from gee_flooding.fig1_tiers import assign_tiers,build_labels_release
from gee_flooding.fig1_publication import city_attributes,run

def test_A_B_C_tiers_include_date_and_primary_overlap():
    df=pd.DataFrame({
        "event_id":["A","B","C","D"],"area_km2":[4,60,250,10],
        "primary_overlap":[.90,.55,.2,.9],"n_candidate_cells":[1,4,20,1],
        "report_span_days":[0,2,6,np.nan]})
    d=assign_tiers(df)
    assert d.spatial_temporal_tier.tolist()==["A","B","C","C"]
    assert d.tier_reason.iloc[3]=="INCOMPLETE_GEOCODE_OR_DATE"

def test_uuid_to_grid_day_to_candidate_clusters(tmp_path):
    root=tmp_path
    inp=tmp_path/"input";inp.mkdir()
    original=pd.DataFrame([
        ("a",1.0,"2022-01-01","2022-01-01"),
        ("b",6.0,"2022-01-01","2022-01-02"),
        ("c",30.0,"2022-01-02","2022-01-03"),
        ("d",70.0,"2022-02-15","2022-02-19"),
    ],columns=["uuid","area_km2","start_date","end_date"])
    original.to_parquet(inp/"raw.parquet",index=False)
    label=pd.DataFrame({
        "event_id":["a","b","c","d"],"grid_id":["1_2"]*4,
        "date":["2022-01-01","2022-01-01","2022-01-02","2022-02-15"],
        "n_candidate_cells":[1,1,2,3],"primary_overlap":[.9,.9,.5,.55],
        "geocode_quality":["HIGH_GEOCODE_SPECIFICITY"]*4})
    label.to_parquet(inp/"primary.parquet",index=False)
    qc=build_labels_release(root,inp/"raw.parquet",inp/"primary.parquet",
                            tag="fig1_publication_test")
    assert qc["raw_source_rows"]==4
    assert qc["geocoded_grid_days"]==3
    assert qc["candidate_contiguous_grid_episodes"]==2
    assert qc["independent_meteorological_storms"] is None
    assert qc["tier_counts"]=={"A":2,"B":1,"C":1}
    # Never merge or drop a primary source UUID.
    with pytest.raises(FileExistsError):
        build_labels_release(root,inp/"raw.parquet",inp/"primary.parquet",
                             tag="fig1_publication_test")

def test_city_coverage_denominator_and_population_schema(tmp_path):
    c=pd.DataFrame({"city_id":["A","B"],"country":["X","Unknown"],
        "continent":["Asia","Unknown"],"koppen_broad":["Tropical","Arid"],
        "fig1_v3_status":["TRAIN_CANDIDATE","EVIDENCE_SPARSE"],
        "eligible_using_only_development_years":[True,False],
        "lon":[20,21],"lat":[20,21]})
    cross=pd.DataFrame({"grid_id":["1_2"],"city_id":["A"]})
    source=pd.DataFrame({"event_id":["a","b"],"grid_id":["1_2","2_2"],
                         "date":["2023-01-01","2023-02-01"],
                         "spatial_temporal_tier":["A","B"]})
    out,strata,report=city_attributes(c,cross,source)
    assert len(out)==2 and len(report)==2
    assert int(out.raw_uuid_count.sum())==1
    assert int(strata.ucdb_total_cities.sum())==2
    assert out.population_class.eq("Unknown").all()
    pd.DataFrame({"city_id":["A","B"],"population_2020":[150000,4500000]}).to_csv(
        tmp_path/"pop.csv",index=False)
    out,_,_=city_attributes(c,cross,source,city_pop=tmp_path/"pop.csv")
    assert set(out.population_class.astype(str))=={"100–500k","1–5m"}

def test_exact_core_periphery_from_small_10km_tiffs(tmp_path):
    import rasterio
    from rasterio.transform import Affine
    from gee_flooding.fig1_spatial import freeze_periphery
    inputs=tmp_path/"input";inputs.mkdir()
    core=pd.DataFrame({"grid_id":["0_2"],"grid_x":[0],"grid_y":[2],
        "longitude":[.0],"latitude":[.1]})
    core.to_parquet(inputs/"core.parquet",index=False)
    paths=[]
    for i,xoff in enumerate([0,40000]):
        p=inputs/f"p{i}.tif"
        with rasterio.open(p,"w",driver="GTiff",height=4,width=4,count=2,
            dtype="float32",crs="EPSG:6933",
            transform=Affine(10000,0,xoff,0,-10000,40000)) as dst:
            dst.write(np.zeros((4,4),dtype="float32"),1)
            dst.write(np.ones((4,4),dtype="float32"),2)
        paths.append(p)
    qc=freeze_periphery(tmp_path,inputs/"core.parquet",*paths,tag="fig1_p_test")
    assert qc["status"]=="PASS_FROZEN_SPATIAL_LATTICE"
    assert qc["urban_core_cells"]==1
    assert qc["valid_one_cell_periphery"]==5  # core at first stripe left edge
    frame=pd.read_parquet(tmp_path/"outputs/fig1_p_test/grid/gf10_core_periphery_2020.parquet")
    assert frame.grid_id.is_unique

def test_no_external_physical_or_storm_proxy_inference(tmp_path):
    c=pd.DataFrame({"city_id":["A"],"country":["X"],"continent":["Asia"],
        "koppen_broad":["Tropical"],"lon":[20.],"lat":[20.],
        "fig1_v3_status":["TRAIN_CANDIDATE"],
        "eligible_using_only_development_years":[True]})
    x=pd.DataFrame({"grid_id":["1_2"],"city_id":["A"]})
    t=pd.DataFrame({"event_id":["a"],"grid_id":["1_2"],"date":["2022-01-01"],
        "spatial_temporal_tier":["A"]})
    out,_,_=city_attributes(c,x,t)
    assert out.prediction_validated.eq(False).all()
