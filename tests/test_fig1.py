"""Tests use synthetic data only, never Groundsource or external network."""
import json
from datetime import date
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from gee_flooding.fig1 import (check_label_contract,candidate_catalogue_overlap,
                               stable_city_split,read_gfid,assign_dominant_city)

def qc_for(n=3):
    return {"status":"PASS_LABEL_GEOCODE_AUDIT","rows_processed":n,
            "count_by_status":{"MATCHED":2,"NOT_IN_GF10_URBAN_DOMAIN":1},
            "count_by_quality":{"HIGH_GEOCODE_SPECIFICITY":2,
                                "MEDIUM_GEOCODE_SPECIFICITY":0,
                                "LOW_GEOCODE_SPECIFICITY":0,"NOT_ELIGIBLE":1}}

def test_primary_label_count_contract():
    news=pd.DataFrame({"event_id":["x","y"],"grid_id":["1_2","1_2"],
                       "geocode_quality":["HIGH_GEOCODE_SPECIFICITY"]*2})
    grid=pd.DataFrame({"grid_id":["1_2"]})
    assert check_label_contract(news,qc_for(),grid)==3
    with pytest.raises(ValueError,match="not unique"):
        check_label_contract(news.assign(event_id=["x","x"]),qc_for(),grid)
    with pytest.raises(ValueError,match="reconcile"):
        bad=qc_for();bad["count_by_quality"]["HIGH_GEOCODE_SPECIFICITY"]=1
        check_label_contract(news,bad,grid)

def test_gfid_candidate_match_with_joint_date_distance():
    news=pd.DataFrame([
        {"grid_id":"1_0","date":pd.Timestamp("2023-01-10"),"lon":30.1,"lat":10.1,"news_count":2},
        {"grid_id":"2_0","date":pd.Timestamp("2023-01-10"),"lon":105.,"lat":10.,"news_count":1},
        {"grid_id":"3_0","date":pd.Timestamp("2023-03-10"),"lon":30.1,"lat":10.1,"news_count":1}])
    ref=pd.DataFrame([
        {"family":"DFO","start":pd.Timestamp("2023-01-07"),
         "end":pd.Timestamp("2023-01-12"),"lon":30.,"lat":10.},
        {"family":"EMDAT","start":pd.Timestamp("2022-01-10"),
         "end":pd.Timestamp("2022-01-12"),"lon":30.,"lat":10.}])
    pairs=candidate_catalogue_overlap(news,ref,radius_km=75,days=7)
    assert len(pairs)==1
    assert pairs.family.iloc[0]=="DFO"
    assert pairs.news_count.iloc[0]==2
    assert pairs.grid_id.iloc[0]=="1_0"

def test_gfid_aggregated_excel_source_families(tmp_path):
    x=tmp_path/"AggregatedFloodData.xlsx"
    pd.DataFrame({"Source":["DFO","EM-DAT","Unknown"],
                  "Start Date":[pd.Timestamp("2021-06-01")]*3,
                  "End Date":[pd.Timestamp("2021-06-03")]*3,
                  "Lat":[10.,11.,12.],"Lon":[20.,21.,22.]}).to_excel(
                    x,sheet_name="Aggregated",index=False)
    catalog,qc=read_gfid(x)
    assert set(catalog.family)=={"DFO","EMDAT"}
    assert qc["raw_gfid_rows"]==3
    assert qc["unusable_or_unknown_source"]==1

def test_predeclared_holdout_is_disjoint():
    df=pd.DataFrame({"city_id":[str(i) for i in range(20)],
                     "continent":["Africa"]*20,"koppen_broad":["Tropical"]*20,
                     "eligible":[True]*15+[False]*5})
    a=stable_city_split(df);b=stable_city_split(df.sample(frac=1,random_state=2))
    assert set(a[a.study_status=="HELDOUT_CITY_CANDIDATE"].city_id)==set(
        b[b.study_status=="HELDOUT_CITY_CANDIDATE"].city_id)
    assert not set(a[a.study_status=="EVIDENCE_SPARSE"].city_id)&set(
        a[a.study_status=="TRAIN_CANDIDATE"].city_id)

def test_area_dominant_city_crosswalk():
    import geopandas as gpd
    cities=gpd.GeoDataFrame({"city_id":["C","D"]},geometry=[
        box(10000,20000,19900,30000),box(19900,20000,22000,30000)],crs=6933)
    grid=pd.DataFrame({"grid_id":["1_2"],"grid_x":[1],"grid_y":[2]})
    match=assign_dominant_city(grid,cities)
    assert len(match)==1 and match.city_id.iloc[0]=="C"
