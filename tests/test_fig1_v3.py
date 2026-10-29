"""Synthetic-only Figure 1 v3 quality-gate tests; no E drive or cloud."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer

from gee_flooding.fig1_v3_gfid import gfid_audit,candidate_sensitivity
from gee_flooding.fig1_v3_city import city_v3_audit,annotation_queue
from gee_flooding.fig1_v3_physical import validate_reference
from gee_flooding.fig1_v3 import build

def make_gfid(path):
    pd.DataFrame([
      {"ID":"D1","Source":"DesInventar","Start Date":pd.NaT,
       "End Date":pd.NaT,"Date":pd.Timestamp("2022-05-02"),"Lat":10.,"Lon":20.},
      {"ID":"E1","Source":"EM-DAT","Start Date":pd.Timestamp("2022-05-03"),
       "End Date":pd.NaT,"Date":pd.NaT,"Lat":10.,"Lon":20.},
      {"ID":"DF1","Source":"DFO","Start Date":pd.Timestamp("2022-05-02"),
       "End Date":pd.Timestamp("2022-05-04"),"Date":pd.NaT,"Lat":11.,"Lon":21.},
      {"ID":"H1","Source":"HANZE","Start Date":"2022",
       "End Date":pd.NaT,"Date":"2022","Lat":11.,"Lon":21.},
      {"ID":"XX","Source":"Unknown","Start Date":pd.Timestamp("2022-05-02"),
       "End Date":pd.NaT,"Date":pd.NaT,"Lat":11.,"Lon":21.},
    ]).to_excel(path,sheet_name="Aggregated",index=False)

def test_gfid_precise_date_fallback_maintains_source_ledger(tmp_path):
    file=tmp_path/"gfid.xlsx";make_gfid(file)
    accepted,audit,reason,qc=gfid_audit(file)
    assert len(audit)==5 and qc["raw_rows"]==5
    assert len(accepted)==3
    assert "DESINVENTAR" in set(accepted.family)
    assert accepted.imputed_one_day_end.sum()==2
    assert accepted.source_date_fallback.sum()==1
    assert qc["reason_counts"]["MISSING_OR_IMPRECISE_START"]==1
    assert qc["reason_counts"]["UNKNOWN_SOURCE"]==1
    assert int(reason.n.sum())==5

def test_city_pre2024_eligibility_and_ucdb_omissions():
    news=pd.DataFrame([
        ("a","1_2","2022-01-01"),("b","1_2","2023-01-01"),
        ("c","1_2","2024-01-01"),("d","2_2","2024-01-01"),
        ("e","2_2","2025-01-01")
    ],columns=["event_id","grid_id","date"])
    news["geocode_quality"]="HIGH_GEOCODE_SPECIFICITY"
    grid=pd.DataFrame({"grid_id":["1_2","2_2"],"urban_fraction_2020":[.4,.06]})
    dominant=pd.DataFrame({"grid_id":["1_2"],"city_id":["A"]})
    cities=pd.DataFrame({"city_id":["A","B"],"continent":["Asia","Asia"],
                         "koppen_broad":["Temperate","Temperate"],
                         "lon":[20,21],"lat":[30,31]})
    city,missing,strata,high,qc=city_v3_audit(news,grid,dominant,cities,
                                               min_news=2,min_years=2)
    assert qc["all_high_reports"]==5
    assert qc["unassigned_high_reports"]==2
    assert qc["development_eligible_cities"]==1
    assert city.set_index("city_id").loc["A","future_high_reports"]==1
    assert "OUTSIDE_UCDB_URBAN_CENTRE" in set(missing.assignment_class)
    sampled=annotation_queue(news,high,total=30)
    assert set(["inclusion_probability","reviewer_id","location_verified"]).issubset(sampled)

def test_physical_strict_nonnegative_and_external_review(tmp_path):
    cells=pd.DataFrame({"grid_id":["1_2"]})
    tf=Transformer.from_crs(6933,4326,always_xy=True)
    lon,lat=tf.transform(15000,25000)
    high=pd.DataFrame({"grid_id":["1_2"],"date":["2023-05-03"]})
    record={ "source_record_id":"p1","source_family":"IN_SITU","observation_date":"2023-05-03",
       "longitude":lon,"latitude":lat,"observation_type":"IN_SITU_SENSOR",
       "pluvial_class":"CONFIRMED_PLUVIAL","valid_spatiotemporal_coverage":"YES",
       "independent_source_confirmed":"YES","reviewer_id":"two-person-audit",
       "evidence_uri":"https://example.org/physical/p1","location_precision_m":30,
       "flood_observed":"YES"}
    path=tmp_path/"physical.csv";pd.DataFrame([record]).to_csv(path,index=False)
    _,positive,qc=validate_reference(path,cells,high)
    assert qc["confirmed_pluvial_with_high_news"]==1
    assert positive.grid_id.tolist()==["1_2"]
    record["independent_source_confirmed"]="NO"
    pd.DataFrame([record]).to_csv(path,index=False)
    with pytest.raises(ValueError,match="Unreviewed"):
        validate_reference(path,cells,high)

def test_v3_pipeline_synthetic_approved_outputs(tmp_path):
    input_dir=tmp_path/"input";input_dir.mkdir()
    grid=pd.DataFrame({"grid_id":["1_2","2_2"],"grid_x":[1,2],"grid_y":[2,2],
        "longitude":[.15,.24],"latitude":[.25,.25],
        "urban_fraction_2020":[.4,.08]})
    grid_path=input_dir/"grid.parquet";grid.to_parquet(grid_path,index=False)
    labels=pd.DataFrame([("a","1_2","2022-05-02","HIGH_GEOCODE_SPECIFICITY"),
                         ("b","1_2","2023-05-02","HIGH_GEOCODE_SPECIFICITY"),
                         ("c","2_2","2024-05-02","HIGH_GEOCODE_SPECIFICITY")],
        columns=["event_id","grid_id","date","geocode_quality"])
    labels_path=input_dir/"primary.parquet";labels.to_parquet(labels_path,index=False)
    qc={"status":"PASS_LABEL_GEOCODE_AUDIT","rows_processed":4,
        "count_by_status":{"MATCHED":3,"NOT_IN_GF10_URBAN_DOMAIN":1},
        "count_by_quality":{"HIGH_GEOCODE_SPECIFICITY":3,
                            "MEDIUM_GEOCODE_SPECIFICITY":0,
                            "LOW_GEOCODE_SPECIFICITY":0,"NOT_ELIGIBLE":1}}
    label_qc=input_dir/"qc.json";label_qc.write_text(json.dumps(qc))
    v2=input_dir/"v2";v2.mkdir()
    pd.DataFrame({"grid_id":["1_2"],"city_id":["A"]}).to_parquet(
        v2/"fig1_grid_dominant_ucdb.parquet",index=False)
    pd.DataFrame({"city_id":["A","B"],"lon":[.15,.24],"lat":[.25,.25],
                  "continent":["Asia","Asia"],"country":["Example","Example"],
                  "koppen_broad":["Temperate","Temperate"]}).to_csv(
        v2/"fig1_ucdb_city_sample_audit.csv",index=False)
    excel=input_dir/"gfid.xlsx";make_gfid(excel)
    result=build(tmp_path,labels_path,grid_path,label_qc,v2,excel,
                 tag="fig1_v3_ci",fast=True,review_n=50)
    out=tmp_path/"outputs/fig1_v3_ci"
    assert result["source_original_raw_rows"]==4
    assert result["news_mapped_high_count"]==3
    assert result["city_audit"]["unassigned_high_reports"]==1
    assert result["gfid_audit"]["accepted_by_family"]["DESINVENTAR"]==1
    assert result["sensitivity_is_full_data"] is False
    for name in ("Figure1_GEE_v3.pdf","Figure1_GEE_v3.png","Figure1_GEE_v3.svg",
        "fig1_v3_qc.json","gfid_reason_by_family.csv",
        "ucdb_missing_assignment_by_period_and_urban_share.csv",
        "independent_groundsource_annotation_queue.csv",
        "physical_evidence_input_template.csv"):
        assert (out/name).exists(),name


def test_possible_duplicate_file_does_not_delete_or_guess(tmp_path):
    from gee_flooding.fig1_v3_gfid import potential_duplicate_audit
    events=pd.DataFrame({"event_id":["AA","BB","CC"]})
    f=tmp_path/"Potential_Duplicate_Events.csv"
    pd.DataFrame({"Event_ID":["AA","CC"],"Paired_ID":["BB","BB"]}).to_csv(f,index=False)
    flagged,qc=potential_duplicate_audit(f,events)
    assert flagged=={"AA","CC"}
    assert qc["status"]=="POSSIBLE_OVERLAPS_ONLY"
    assert qc["raw_potential_duplicate_pairs"]==2
    pd.DataFrame({"Unknown_Field":["z"]}).to_csv(f,index=False)
    flagged,qc=potential_duplicate_audit(f,events)
    assert flagged==set()
    assert qc["status"]=="UNRESOLVED_ID_SCHEMA"

def test_manual_review_requires_traceable_independent_source():
    from gee_flooding.fig1_v3_city import annotate_summary
    reviewed=pd.DataFrame({
        "event_id":["a"],"location_verified":["YES"],"date_verified":["YES"],
        "flood_occurrence_verified":["YES"],"independent_of_groundsource":["YES"],
        "inclusion_probability":[.2],"reviewer_id":[""],"evidence_source_uri":[""]})
    assert annotate_summary(reviewed)["reviewed_independent_rows"]==0
    reviewed.loc[0,"reviewer_id"]="Reviewer 1"
    reviewed.loc[0,"evidence_source_uri"]="https://example.org/event"
    assert annotate_summary(reviewed)["reviewed_independent_rows"]==1
