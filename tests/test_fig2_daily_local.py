import json
import numpy as np
import pandas as pd
import pytest
from gee_flooding import fig2_daily,fig2_3h


def test_frozen_daily_utc_exposure_independent_of_news_and_prior_7days(tmp_path):
    g=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],"grid_y":[0,0],
                  "urban_fraction_2020":[.2,.6]}).to_parquet(g,index=False)
    city=tmp_path/"city.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"city_id":["U0","U1"]}).to_parquet(city,index=False)
    static=tmp_path/"static";static.mkdir()
    s=static/"fig2_GF10_resilience_indicators.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"urban_fraction_2020":[.2,.6],
        "hand_m":[2,4],"slope_deg":[1,2],"upstream_area_km2":[20,40],"vegetation_fraction":[.25,.5],
        "built_fraction_2020":[.2,.4],"built_neighbor_density":[.3,.4],
        "built_fragmentation":[.1,.1],
        "built_growth_2000_2020":[.08,.12]}).to_parquet(s,index=False)
    (static/"fig2_GF10_indicator_merge_qc.json").write_text(json.dumps({
        "n_conflicts":0,"frozen_grid_count":2}))
    dates=pd.date_range("2023-12-25","2024-01-03")
    r=[]
    for gid in ["0_0","1_0"]:
        for d in dates:
            r.append({"grid_id":gid,"date":d,
                      "rain_d_mm":30 if d==pd.Timestamp("2024-01-02") else 1,
                      "precipitation_cnt":48})
    rain=tmp_path/"rain.parquet";pd.DataFrame(r).to_parquet(rain,index=False)
    peak=tmp_path/"peak.parquet"
    pd.DataFrame({"grid_id":[x["grid_id"] for x in r if x["date"]>=pd.Timestamp("2024-01-01")],
                  "date":[x["date"] for x in r if x["date"]>=pd.Timestamp("2024-01-01")],
                  "rain_3h_mm":[12]*6}).to_parquet(peak,index=False)
    manifest=fig2_daily.build(tmp_path,g,city,rain,peak,s,
             "2024-01-01","2024-01-03","fig2_daily_fixture")
    assert manifest["n_declared_grid_days"]==6
    assert manifest["n_storm_exposures"]==6
    assert manifest["n_storm_objects"]>=1
    out=tmp_path/"data"/"derived"/"fig2_daily_fixture"
    w=pd.read_parquet(out/"storm_exposure_weather.parquet")
    assert set(["rain_3h_mm","rain_24h_mm","api_7d_mm","storm_id"])<=set(w)
    assert w.loc[w.date.eq(pd.Timestamp("2024-01-01")),"api_7d_mm"].tolist()==[7.,7.]
    bad=tmp_path/"bad.parquet"
    rr=pd.read_parquet(rain)
    rr.loc[0,"precipitation_cnt"]=47
    rr.to_parquet(bad,index=False)
    with pytest.raises(ValueError,match="valid retrieval count"):
        fig2_daily.build(tmp_path,g,city,bad,peak,s,
             "2024-01-01","2024-01-03","fig2_daily_incomplete")
    with pytest.raises(FileExistsError):
        fig2_daily.build(tmp_path,g,city,rain,peak,s,
             "2024-01-01","2024-01-03","fig2_daily_fixture")


def test_three_hour_bins_not_labeled_rolling_and_reject_missing(tmp_path):
    times=pd.date_range("2024-07-01","2024-07-01 21:00",freq="3h")
    source=tmp_path/"aligned_3hour.csv"
    pd.DataFrame({"grid_id":["0_0"]*8,
                  "timestamp_utc":times,"precip_3h_mm":np.arange(8)}).to_csv(source,index=False)
    out=fig2_3h.collapse(tmp_path,source,"fig2_threehour_fixture")
    assert out["n_3h_bins"]==8
    data=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_threehour_fixture"/
                         "fig2_daily_max_aligned_3h_GF10.parquet")
    assert data.rain_3h_mm.iloc[0]==7
    x=pd.read_csv(source).iloc[:-1]
    x.to_csv(source,index=False)
    with pytest.raises(ValueError,match="Incomplete"):
        fig2_3h.collapse(tmp_path,source,"fig2_threehour_incomplete")


def test_cf_latlon_projected_area_sum(tmp_path):
    xr=pytest.importorskip("xarray")
    from gee_flooding import fig2_cf_grid
    grid=tmp_path/"g.parquet"
    pd.DataFrame({"grid_id":["0_0"],"grid_x":[0],"grid_y":[0]}).to_parquet(grid,index=False)
    lat=np.array([-.05,.05,.15]);lon=np.array([-.05,.05,.15])
    nc=tmp_path/"rain.nc"
    data=np.full((1,3,3),10.,dtype="float32")
    ds=xr.Dataset({"precipitation":(("time","lat","lon"),data,
                   {"units":"mm/day"}),
                   "precipitation_cnt":(("time","lat","lon"),
                   np.full_like(data,48),{"units":"count"})},
                  coords={"time":pd.date_range("2024-07-01",periods=1),
                          "lat":lat,"lon":lon})
    ds.to_netcdf(nc)
    output=fig2_cf_grid.extract(tmp_path,grid,[nc],
        "precipitation:rain_d_mm,precipitation_cnt:precipitation_cnt",
        "fig2_cf_fixture")
    assert output.rain_d_mm.iloc[0]==pytest.approx(10,abs=.001)
    assert output.precipitation_cnt.iloc[0]==pytest.approx(48,abs=.001)


def test_true_rolling_3h_uses_six_bin_rain_rate_and_no_fake_hours(tmp_path):
    from gee_flooding import fig2_rolling3h
    start=pd.Timestamp("2024-07-01")
    times=pd.date_range(start-pd.Timedelta(minutes=150),
                        start+pd.Timedelta(hours=23,minutes=30),freq="30min")
    x=pd.DataFrame({"grid_id":["0_0"]*len(times),
                    "timestamp_utc":times,
                    "precipitation_rate_mm_h":[2.0]*len(times)})
    p=tmp_path/"halfhour.parquet"
    x.to_parquet(p,index=False)
    q=fig2_rolling3h.build(tmp_path,[p],"2024-07-01","2024-07-01",
                            "fig2_rolling_fixture")
    assert q["n_gf10_days"]==1
    df=pd.read_parquet(tmp_path/"data"/"derived"/"fig2_rolling_fixture"/
                       "fig2_daily_rolling_3h_max_GF10.parquet")
    assert df.rain_3h_mm.iloc[0]==pytest.approx(6.0)
    x=x.iloc[1:].copy()
    x.to_parquet(p,index=False)
    with pytest.raises(ValueError,match="Incomplete"):
        fig2_rolling3h.build(tmp_path,[p],"2024-07-01","2024-07-01",
                              "fig2_rolling_missing")
