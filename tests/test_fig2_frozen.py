import json
import numpy as np
import pandas as pd
import pytest

from gee_flooding import fig2_frozen, fig2_gee_weekly, fig2_prepare, fig2


def fake_paper(tmp_path):
    rng=np.random.default_rng(321)
    rows=[]
    cities=[]
    for k in range(18):
        city=f"UC{k:03d}"
        state="TRAIN_CANDIDATE" if k<10 else "HELDOUT_CITY_CANDIDATE"
        cities.append({"city_id":city,"fig1_v3_status":state,
                       "eligible_using_only_development_years":True})
        for year in range(2021,2026):
            for st in range(8):
                for cell in range(3):
                    vals={
                        "rain_24h_mm":float(rng.uniform(18,80)),
                        "rain_3h_mm":float(rng.uniform(8,35)),
                        "api_7d_mm":float(rng.uniform(0,120)),
                        "hand_m":float(rng.uniform(0,20)),
                        "slope_deg":float(rng.uniform(0,12)),
                        "urban_fraction_2020":float(rng.random()),
                        "vegetation_fraction":float(rng.random()),
                        "built_fraction_2020":float(rng.random()),
                        "built_neighbor_density":float(rng.random()),
                        "built_fragmentation":float(rng.random()),
                        "built_growth_2000_2020":float(rng.uniform(-.2,.35)),
                    }
                    rows.append({
                        "grid_id":f"{k*10+cell}_0",
                        "date":f"{year}-06-{st+1:02d}",
                        "city_id":city,
                        "storm_id":f"independent_{year}_{k}_{st}",
                        "observed_news_onset":int(rng.random()<.34),
                        "target_semantics":fig2.TARGET,**vals})
    panel=tmp_path/"panel.parquet"
    audit=tmp_path/"fig1_v3_city.csv"
    contract=tmp_path/"weather_contract.json"
    pd.DataFrame(rows).to_parquet(panel,index=False)
    pd.DataFrame(cities).to_csv(audit,index=False)
    contract.write_text(json.dumps({
        "meteorology_source":"NASA/GPM_L3/IMERG_V07",
        "exposure_sampling_rule":"all predeclared urban-grid days independently wet",
        "storms_independent_of_labels":True,
        "coverage_complete_within_scope":True,
        "spatial_scope":"synthetic fixture","start_date":"2021-01-01",
        "end_date":"2025-12-31","time_basis":"UTC","rain_units":"mm"}))
    return panel,audit,contract


def test_frozen_2024_25_and_independent_city_exclusion(tmp_path,monkeypatch):
    panel,audit,contract=fake_paper(tmp_path)
    df,_=fig2_frozen.freeze(panel,audit,contract)
    comparisons,failed=fig2_frozen.prospective_splits(df)
    assert len(comparisons)==3, failed
    for name,(tr,te,removed) in comparisons.items():
        assert set(df.iloc[tr].year)=={2021,2022,2023}
        assert not set(df.iloc[tr].storm_id)&set(df.iloc[te].storm_id)
        if name.startswith("prospective"):
            assert set(df.iloc[te].year)=={2024,2025}
        if name.endswith("new_city"):
            assert not set(df.iloc[tr].city_id)&set(df.iloc[te].city_id)
    monkeypatch.setattr(fig2_frozen,"paired_delta_ci",
                        lambda y,p0,p1,clusters,seed=42,replications=400:(-.1,.1,50))
    qc=fig2_frozen.run(tmp_path,panel,audit,contract,
                       tag="fig2_frozen_synthetic",algorithms=("logistic",))
    assert qc["require_all_three_comparisons_for_complete_transfer"]
    assert qc["no_external_physical_evidence_in_this_module"]
    out=tmp_path/"outputs"/"fig2_frozen_synthetic"
    metrics=pd.read_csv(out/"fig2_frozen_prospective_ablation.csv")
    assert set(metrics.model)==set(fig2_frozen.CORE)
    assert set(metrics.comparison)==set(comparisons)
    assert (out/"Figure2_frozen_prospective_support.pdf").exists()
    with pytest.raises(FileExistsError):
        fig2_frozen.run(tmp_path,panel,audit,contract,tag="fig2_frozen_synthetic",
                        algorithms=("logistic",))


def test_frozen_audit_rejects_2024_25_chosen_cities(tmp_path):
    panel,audit,contract=fake_paper(tmp_path)
    d=pd.read_csv(audit)
    d=d.drop(columns=["eligible_using_only_development_years"])
    d.to_csv(audit,index=False)
    with pytest.raises(ValueError,match="development-year"):
        fig2_frozen.freeze(panel,audit,contract)


def test_paired_bootstrap_uses_same_clusters():
    rng=np.random.default_rng(14)
    y=np.tile([0,1,0,1,0],20)
    p0=np.clip(.3+.15*y+rng.normal(0,.12,len(y)),.01,.99)
    p1=np.clip(.2+.5*y+rng.normal(0,.12,len(y)),.01,.99)
    groups=np.repeat(np.arange(20),5)
    lo,hi,n=fig2_frozen.paired_delta_ci(y,p0,p1,groups,seed=42,replications=80)
    assert n>=30
    assert lo>0
    assert hi>=lo


def test_weekly_dry_run_is_bounded_and_uses_dates(tmp_path):
    grid=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],
                  "grid_y":[0,0],"urban_fraction_2020":[.1,.2]}).to_parquet(grid)
    x=fig2_gee_weekly.launch(grid,"2024-01-01",7,0,2)
    assert not x["task_submitted"]
    assert x["n_expected_grid_days"]==14
    assert x["description"]=="f2_weather_week_20240101_07_000000_000001"
    with pytest.raises(ValueError):
        fig2_gee_weekly.plan("2024-01-01",8,1)
    with pytest.raises(ValueError):
        fig2_gee_weekly.plan("2026-01-01",1,1)


def test_weekly_import_rejects_mismatched_utc_date(tmp_path):
    df=pd.DataFrame({"grid_id":["0_0","1_0"],"date":["2024-02-01","2024-02-02"]})
    path=tmp_path/"f2_weather_week_20240201_07_000000_000001.csv"
    df.to_csv(path,index=False)
    loaded=fig2_prepare.load_exports(tmp_path,"f2_weather_")
    assert len(loaded)==2
    df.loc[1,"date"]="2024-03-01"
    df.to_csv(path,index=False)
    with pytest.raises(ValueError,match="outside declared"):
        fig2_prepare.load_exports(tmp_path,"f2_weather_")
