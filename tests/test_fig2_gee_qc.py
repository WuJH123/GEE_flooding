import json
import numpy as np
import pandas as pd
import pytest
from gee_flooding import fig2_gee,fig2_gee_qc,fig2_backfill_plan


def fixture(tmp_path):
    grid=tmp_path/"gf10.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],"grid_y":[0,0],
                  "urban_fraction_2020":[.5,.4]}).to_parquet(grid,index=False)
    joined=tmp_path/"merged.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],
                  "built_fraction_2020":[.5,.2],
                  "built_area_km2_2020":[50.,20.]}).to_parquet(joined,index=False)
    fig2_backfill_plan.plan(tmp_path,grid,joined,tag="fig2_import_plan_test",max_cells=20)
    return tmp_path/"data"/"reference"/"fig2_import_plan_test",joined


def exports(plan,static,exposure):
    bands={"hand_m":2.5,"slope_deg":1.2,"upstream_area_km2":55.,
           "vegetation_fraction":.2,"built_neighbor_density":.35,
           "built_fragmentation":.12,"built_growth_2000_2020":.06,
           "population_count_2020":5000.,
           "built_nres_area_km2_2020":15.}
    tasks=pd.read_csv(plan/"fig2_gee_backfill_tasks.csv")
    for row in tasks.itertuples(index=False):
        grid=plan/row.grid_file
        source=pd.read_parquet(grid)
        run=fig2_gee.launch(grid,0,row.n_grid,row.mode,None,
                            "GEE_flooding_Figure2",bands=row.bands)
        dst=static if row.mode=="static" else exposure
        data={"grid_id":source.grid_id,
              "urban_fraction_2020":source.urban_fraction_2020}
        for b in row.bands.split(","):
            data[b]=bands[b]
        pd.DataFrame(data).to_csv(dst/(run["description"]+".csv"),index=False)


def test_actual_export_manifest_matching_and_no_silent_missing(tmp_path):
    plan,local=fixture(tmp_path)
    static=tmp_path/"static"
    exp=tmp_path/"exposure"
    static.mkdir();exp.mkdir()
    qc=fig2_gee_qc.audit(tmp_path,plan,static,exp,local=local,tag="fig2_audit_missing")
    assert qc["status"]=="PARTIAL" and qc["n_valid"]==0
    with pytest.raises(ValueError,match="failed closed"):
        fig2_gee_qc.audit(tmp_path,plan,static,exp,local=local,
                          tag="fig2_audit_missing_strict",require_complete=True)
    exports(plan,static,exp)
    ok=fig2_gee_qc.audit(tmp_path,plan,static,exp,local=local,
                          tag="fig2_audit_complete",require_complete=True)
    assert ok["status"]=="ALL_TASK_CSVS_SCHEMA_PASSED"
    assert ok["n_valid"]==4
    assert ok["n_invalid"]==0


def test_grid_and_physical_value_contract_violations_are_rejected(tmp_path):
    plan,local=fixture(tmp_path)
    static=tmp_path/"static"
    exp=tmp_path/"exposure"
    static.mkdir();exp.mkdir()
    exports(plan,static,exp)
    target=next(static.glob("f2_static_*.csv"))
    x=pd.read_csv(target)
    col=[k for k in x if k not in ("grid_id","urban_fraction_2020")][0]
    x.loc[0,col]=np.nan
    x.to_csv(target,index=False)
    with pytest.raises(ValueError,match="failed closed"):
        fig2_gee_qc.audit(tmp_path,plan,static,exp,local=local,
                          tag="fig2_bad_missing",require_complete=True)
    report=json.loads((tmp_path/"reports"/"fig2_bad_missing"/
                       "fig2_gee_postdownload_qc.json").read_text())
    assert report["status"]=="REJECTED"


def test_2020_jrc_independent_shadow_detects_area_drift(tmp_path):
    _,local=fixture(tmp_path)
    exp=tmp_path/"shadow"
    exp.mkdir()
    pd.DataFrame({"grid_id":["0_0","1_0"],"built_area_km2_2020":[50.2,20.1]}).to_csv(
        exp/"f2_exposure_2020_000000_000001_bshadow.csv",index=False)
    result=fig2_gee_qc.check_independent_built_area(local,exp)
    assert result["status"]=="LOCAL_VS_GEE_SOURCE_CROSSCHECK"
    pd.DataFrame({"grid_id":["0_0","1_0"],"built_area_km2_2020":[60.,20.1]}).to_csv(
        exp/"f2_exposure_2020_000000_000001_bshadow.csv",index=False)
    bad=fig2_gee_qc.check_independent_built_area(local,exp)
    assert bad["status"]=="FAILED_SOURCE_CONSERVATION"
    assert bad["n_flagged"]==1
