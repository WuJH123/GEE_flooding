"""Figure1 priority QA tests: synthetic, no E-drive, no GEE network."""
import json
import pandas as pd
import pytest
from gee_flooding.fig1_preflight import inspect
from gee_flooding.fig1_gee_pilot import prepare,run_gee
from gee_flooding.fig1_review import summarize

def test_preflight_guards_ledger_and_existing_file_schemas(tmp_path):
    inp=tmp_path/"input";inp.mkdir()
    pd.DataFrame({"uuid":["a"],"geometry":[b"blob"],"area_km2":[1.],
                  "start_date":["2022-01-01"],"end_date":["2022-01-01"]}).to_parquet(inp/"raw.parquet")
    pd.DataFrame({"event_id":["a"],"grid_id":["1_2"],"date":["2022-01-01"],
       "primary_overlap":[.9],"n_candidate_cells":[1],"geocode_quality":["HIGH_GEOCODE_SPECIFICITY"]}).to_parquet(inp/"mapped.parquet")
    pd.DataFrame({"grid_id":["1_2"],"grid_x":[1],"grid_y":[2],
          "longitude":[0.],"latitude":[0.]}).to_parquet(inp/"grid.parquet")
    pd.DataFrame({"city_id":["a"],"continent":["Asia"],"koppen_broad":["Arid"],
           "fig1_v3_status":["TRAIN_CANDIDATE"]}).to_csv(inp/"city.csv",index=False)
    (inp/"v3.json").write_text(json.dumps({"gfid_audit":{"raw_rows":136642},
                "sensitivity_is_full_data":True,
                "city_audit":{"all_high_reports":1788759,
                  "assigned_high_reports":1086280,"unassigned_high_reports":702479}}))
    (inp/"cross.parquet").write_bytes(b"metadata")
    with pytest.raises(ValueError,match="raw_news changed"):
        inspect(tmp_path,inp/"raw.parquet",inp/"mapped.parquet",inp/"grid.parquet",
                inp/"city.csv",inp/"v3.json",inp/"cross.parquet","fig1_test")

def test_weather_pilot_selects_strata_and_no_GEE_until_submit(tmp_path):
    f=tmp_path/"input";f.mkdir()
    tier=pd.DataFrame({"grid_id":["1_2","1_2","2_2","3_2","4_2"],
        "date":["2010-06-01","2010-06-01","2023-01-02","2024-08-15","2025-04-20"],
        "spatial_temporal_tier":["A","B","C","A","B"]})
    tier.to_parquet(f/"tiers.parquet")
    grid=pd.DataFrame({"grid_id":["1_2","2_2","3_2","4_2"],
         "grid_x":[1,2,3,4],"grid_y":[2]*4,
         "longitude":[10,20,30,40],"latitude":[1,-1,1,-1]})
    grid.to_parquet(f/"grid.parquet")
    qc=prepare(tmp_path,f/"tiers.parquet",f/"grid.parquet","pilot_test",n=4)
    assert qc["n"]==4
    manifest=tmp_path/"outputs/pilot_test/gee/fig1_imerg_pilot_manifest.csv"
    d=pd.read_csv(manifest)
    assert d[["grid_id","date"]].drop_duplicates().shape[0]==4
    assert "B" not in d[(d.grid_id=="1_2")].spatial_temporal_tier.tolist()
    r=run_gee("fake-no-auth-needed",manifest,max_rows=3)
    assert r["status"]=="DRY_RUN_NOT_SUBMITTED"
    assert r["rows"]==3
    with pytest.raises(ValueError,match=">25 rows"):
        run_gee("fake",manifest,max_rows=100)

def test_label_review_rejects_unreviewed_as_accuracy(tmp_path):
    p=tmp_path/"input";p.mkdir()
    q=pd.DataFrame({
       "event_id":["a","b"],"geocode_quality":["HIGH_GEOCODE_SPECIFICITY","LOW_GEOCODE_SPECIFICITY"],
       "assignment_class":["WITHIN_UCDB_URBAN_CENTRE","OTHER_OR_NO_UCDB"],
       "era":["2021PLUS","PRE2021"],"inclusion_probability":[.2,.1]})
    q.to_csv(p/"queue.csv",index=False)
    r=pd.DataFrame([{
       "event_id":"a","reviewer_id":"reviewer1","evidence_source_uri":"https://source.example/a",
       "independent_of_groundsource":"YES","location_verified":"YES",
       "date_verified":"YES","flood_occurrence_verified":"YES",
       "pluvial_mechanism_verified":"UNKNOWN"}])
    r.to_csv(p/"reviews.csv",index=False)
    out=summarize(tmp_path,p/"queue.csv",p/"reviews.csv","review_pilot")
    assert out["missing"]==1
    assert out["status"]=="REVIEW_INCOMPLETE_NO_ACCURACY_CLAIM"
    assert out["estimates"]=={}
    assert out["peer_review_ready"] is False

def test_label_review_disagreement_blocks_population_estimates(tmp_path):
    p=tmp_path/"input";p.mkdir()
    pd.DataFrame({"event_id":["a"],"geocode_quality":["HIGH_GEOCODE_SPECIFICITY"],
       "assignment_class":["WITHIN_UCDB_URBAN_CENTRE"],
       "era":["2021PLUS"],"inclusion_probability":[.5]}).to_csv(p/"q.csv",index=False)
    base={"event_id":"a","independent_of_groundsource":"YES",
          "evidence_source_uri":"https://example.org/source",
          "date_verified":"YES","flood_occurrence_verified":"YES",
          "pluvial_mechanism_verified":"UNKNOWN"}
    pd.DataFrame([dict(base,reviewer_id="R1",location_verified="YES"),
                  dict(base,reviewer_id="R2",location_verified="NO")]).to_csv(p/"r.csv",index=False)
    out=summarize(tmp_path,p/"q.csv",p/"r.csv","review_disagreement")
    assert out["reviewer_disagreements"]==1
    assert out["estimates"]=={}


def test_paired_reference_never_becomes_flood_free_negative(tmp_path):
    inp=tmp_path/"input";inp.mkdir()
    pd.DataFrame({"grid_id":["1_2","2_2"],"date":["2023-05-10","2023-08-10"],
           "spatial_temporal_tier":["A","B"]}).to_parquet(inp/"tiers.parquet")
    pd.DataFrame({"grid_id":["1_2","2_2"],"grid_x":[1,2],"grid_y":[2,2],
           "longitude":[12.,13.],"latitude":[10.,-10.]}).to_parquet(inp/"grid.parquet")
    qc=prepare(tmp_path,inp/"tiers.parquet",inp/"grid.parquet",
               "pilot_pair",n=2,paired_controls=True)
    assert qc["n_reported_days"]==2
    assert qc["n_unlabeled_reference_days"]==2
    result=pd.read_csv(tmp_path/"outputs/pilot_pair/gee/fig1_imerg_pilot_manifest.csv")
    assert set(result.sample_role)=={"REPORTED_NEWS_DAY","UNLABELED_SAME_GRID_SEASON"}
    assert result.groupby("pair_id").size().to_dict()=={"F1PAIR_0001":2,"F1PAIR_0002":2}
    assert result.iloc[0].sample_role=="REPORTED_NEWS_DAY"
    assert result.iloc[1].sample_role=="UNLABELED_SAME_GRID_SEASON"


def test_gfd_probe_requires_real_frozen_grid_and_known_id(tmp_path):
    from gee_flooding.fig1_gfd_probe import gfd_probe
    g=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["1_2"],"grid_x":[1],"grid_y":[2]}).to_parquet(g)
    dry=gfd_probe("not-connected",g,"1_2",3977,submit=False)
    assert dry["status"]=="DRY_RUN_NOT_SUBMITTED"
    assert dry["physical_verification"] is not True if "physical_verification" in dry else True
    with pytest.raises(ValueError,match="grid_id not found"):
        gfd_probe("not-connected",g,"2_2",3977,submit=False)
