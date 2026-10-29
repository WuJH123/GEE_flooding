import json
import numpy as np
import pandas as pd
import pytest

from gee_flooding import fig2, fig2_gee, fig2_prepare


def _fixture(tmp_path):
    rng=np.random.default_rng(42)
    rows=[]
    for city in range(24):
        for storm in range(24):
            for offset in range(2):
                rows.append(dict(
                    grid_id=f"{city}_{storm}_{offset}",
                    date=f"{2021+storm%5}-06-{1+storm//5:02d}",
                    city_id=f"city{city}", storm_id=f"meteorological_{storm}",
                    country=f"country{city//4}", climate_zone=f"climate{city%4}",
                    observed_news_onset=int(rng.random()<.27),
                    target_semantics=fig2.TARGET,
                    rain_24h_mm=float(rng.uniform(20,90)),
                    rain_3h_mm=float(rng.uniform(10,40)),api_7d_mm=float(rng.uniform(0,130)),
                    hand_m=float(rng.uniform(0,20)),slope_deg=float(rng.uniform(0,10)),
                    urban_fraction_2020=float(rng.random()),
                    vegetation_fraction=float(rng.random()),
                    built_fraction_2020=float(rng.random()),
                    built_neighbor_density=float(rng.random()),
                    built_fragmentation=float(rng.random()),
                    built_growth_2000_2020=float(rng.uniform(-.1,.3)),
                ))
    df=pd.DataFrame(rows)
    panel=tmp_path/"panel.parquet"
    df.to_parquet(panel,index=False)
    contract=tmp_path/"weather.json"
    contract.write_text(json.dumps({
        "meteorology_source":"NASA/GPM_L3/IMERG_V07",
        "exposure_sampling_rule":"all storm exposed GF10 days independent of reporting",
        "storms_independent_of_labels":True, "coverage_complete_within_scope":True,
        "spatial_scope":"synthetic", "start_date":"2021-01-01","end_date":"2025-12-31",
        "time_basis":"UTC","rain_units":"mm",
    }),encoding="utf-8")
    return panel,contract


def test_fig2_locks_news_semantics(tmp_path):
    panel,contract=_fixture(tmp_path)
    d=pd.read_parquet(panel)
    d.loc[0,"target_semantics"]="confirmed_nonflood"
    d.to_parquet(panel,index=False)
    with pytest.raises(ValueError,match="semantics"):
        fig2.prepare(panel)
    with pytest.raises(ValueError,match="External|independent|Meteorological"):
        c=json.loads(contract.read_text())
        c["storms_independent_of_labels"]=False
        contract.write_text(json.dumps(c))
        fig2.validate_contract(contract)


def test_city_storm_holdout_and_complete_fig2_outputs(tmp_path,monkeypatch):
    from sklearn.linear_model import LogisticRegression
    panel,contract=_fixture(tmp_path)
    df=fig2.prepare(panel)
    train,test=fig2._split(df,"city_id",42)
    assert not (set(df.iloc[train].city_id) & set(df.iloc[test].city_id))
    assert not (set(df.iloc[train].storm_id) & set(df.iloc[test].storm_id))
    def fast_fit(X,y,seed,weights=None):
        m=LogisticRegression(max_iter=100)
        m.fit(X,y,sample_weight=weights)
        return m
    monkeypatch.setattr(fig2,"_fit",fast_fit)
    monkeypatch.setattr(fig2,"_bootstrap",lambda y,p,storm,seed,n=150:(.1,.9))
    result=fig2.run(tmp_path,panel,contract,seeds=(42,))
    assert result["status"]=="DRAFT_NEWS_PROXY_ONLY"
    assert result["no_actual_flood_risk_probability"]
    assert result["m5_status"]=="NOT_IDENTIFIABLE_WITHOUT_EXTERNAL_COVERAGE"
    out=tmp_path/"outputs"/"fig2_v1"
    assert (out/"Figure2_news_proxy.pdf").exists()
    assert (out/"Figure2_news_proxy.png").exists()
    metrics=pd.read_csv(out/"fig2_ablation_generalization.csv")
    assert set(fig2.MODELS)-set(["M5_selection_sensitivity"]) <= set(metrics.model)
    with pytest.raises(FileExistsError):
        fig2.run(tmp_path,panel,contract,seeds=(42,))


def test_physical_evidence_is_not_fabricated(tmp_path):
    df=pd.DataFrame({"grid_id":["0_0"],"date":[pd.Timestamp("2023-01-01")],
                     "prediction":[.9],"observed_news_onset":[1]})
    info,_=fig2._physical(df,df,None)
    assert info["status"]=="NOT_AVAILABLE"
    physical=tmp_path/"phys.csv"
    pd.DataFrame([dict(grid_id="0_0",date="2023-01-01",valid_observation=1,
                       flood_observed=1,source_independent=0,pluvial_confirmed=1,
                       sensor="news")]).to_csv(physical,index=False)
    info,_=fig2._physical(df,df,physical)
    assert info["status"]=="NOT_AVAILABLE"


def test_gee_export_is_bounded_dry_run_without_network(tmp_path):
    grid=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],"grid_y":[0,0]}).to_parquet(grid)
    r=fig2_gee.launch(grid,0,2,"weather","2023-09-01","test",submit=False)
    assert r["task_submitted"] is False
    with pytest.raises(ValueError):
        fig2_gee.selected_grid(grid,0,251)


def test_weather_object_ids_ignore_news():
    df=pd.DataFrame({"grid_id":["0_0","1_0","10_0","1_0"],
                     "grid_x":[0,1,10,1], "grid_y":[0,0,0,0],
                     "date":pd.to_datetime(["2023-01-01","2023-01-01",
                                            "2023-01-01","2023-01-02"]),
                     "rain_24h_mm":[25,26,24,29],
                     "rain_3h_mm":[11,11,11,12],
                     "observed_news_onset":[0,0,1,0]})
    x=fig2_prepare.weather_objects(df,radius_km=20)
    assert x.storm_id.nunique()==2
    y=fig2_prepare.weather_objects(df.assign(observed_news_onset=1),radius_km=20)
    assert x.storm_id.tolist()==y.storm_id.tolist()
