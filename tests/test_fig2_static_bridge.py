import json
import pandas as pd
from gee_flooding.fig2_prepare import build


def test_prepare_uses_audited_local_first_static_without_reexport(tmp_path):
    grid=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],"grid_y":[0,0],
                  "urban_fraction_2020":[.4,.6]}).to_parquet(grid,index=False)
    city=tmp_path/"city.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "city_id":["U001","U002"]}).to_parquet(city,index=False)
    local=tmp_path/"merged"
    local.mkdir()
    path=local/"fig2_GF10_resilience_indicators.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "urban_fraction_2020":[.4,.6],
                  "hand_m":[2.0,4.0],"slope_deg":[.1,.2],
                  "vegetation_fraction":[.25,.35],
                  "built_fraction_2020":[.4,.5],
                  "built_neighbor_density":[.3,.4],
                  "built_fragmentation":[.1,.2],
                  "built_growth_2000_2020":[.05,.07]
                  }).to_parquet(path,index=False)
    (local/"fig2_GF10_indicator_merge_qc.json").write_text(json.dumps({
        "frozen_grid_count":2,"n_conflicts":0}),encoding="utf-8")
    wd=tmp_path/"weather"
    wd.mkdir()
    for day in ("20240701","20240702"):
        pd.DataFrame({
            "grid_id":["0_0","1_0"],
            "rain_24h_mm":[30,22],
            "rain_3h_mm":[12,11],
            "api_7d_mm":[80,100],
            "n_obs_24h":[48,48],
            "n_obs_7d":[336,336]
        }).to_csv(wd/f"f2_weather_{day}_000000_000001.csv",index=False)
    qc=build(tmp_path,grid,city,None,wd,None,"2024-07-01","2024-07-02",
             count=2,tag="fig2_prepared_static_bridge",static_parquet=path)
    assert qc["static_source"]=="AUDITED_LOCAL_FIRST_GF10"
    assert qc["coverage_complete_within_scope"]
    assert qc["n_declared_grid_days"]==4
    result=tmp_path/"data"/"derived"/"fig2_prepared_static_bridge"
    assert len(pd.read_parquet(result/"static_grid_factors.parquet"))==2
    assert len(pd.read_parquet(result/"storm_exposure_weather.parquet"))==4
    assert pd.read_parquet(result/"fig2_resilience_all_static_GF10.parquet").shape[1]>=8
