import json

import numpy as np
import pandas as pd
import pytest

from gee_flooding import fig2_static_local
from gee_flooding.fig2_indicators import assemble as merge_sources


def fixture(tmp_path):
    grid=tmp_path/"gf10.parquet"
    pd.DataFrame({
       "grid_id":["0_0","1_0","2_0"],"grid_x":[0,1,2],"grid_y":[0,0,0],
       "urban_fraction_2020":[.2,.7,.4]
    }).to_parquet(grid,index=False)
    base=tmp_path/"ghsl2020";base.mkdir()
    path=base/"fig2_GF10_resilience_indicators.parquet"
    pd.DataFrame({
        "grid_id":["0_0","1_0","2_0"],
        "built_fraction_2020":[.25,.65,.35],
        "built_area_km2_2020":[25,65,35],
    }).to_parquet(path,index=False)
    (base/"fig2_GF10_indicator_merge_qc.json").write_text(json.dumps({
        "status":"PILOT_REQUIRES_REVIEW",
        "frozen_grid_count":3,"n_conflicts":0,"n_missing_core_indicators":9,
        "global_coverage_validated":False
    }))
    return grid,path


def local(tmp_path,tag,column,values,coverage=None):
    base=tmp_path/tag;base.mkdir()
    path=base/"fig2_local_GF10_indicators.parquet"
    ids=["0_0","1_0","2_0"]
    if coverage is None:coverage=[.99,.99,.99]
    pd.DataFrame({
        "grid_id":ids,column:values,
        "coverage_"+column:coverage}).to_parquet(path,index=False)
    expected=fig2_static_local.LOCAL_SEMANTICS[column]
    (base/"fig2_local_exact_qc.json").write_text(json.dumps({
        "status":"LOCAL_EXACT_GF10_SCOPE_COMPLETE_NEEDS_SOURCE_AUDIT",
        "method":"exactextract_native_pixel_fraction_weighted",
        "grid_crs":"EPSG:6933",
        "grid_cell_count":3,
        "min_pixel_coverage":.95,
        "indicator_coverage":{column:{"valid_n":int(sum(pd.notna(values))),
                                     "coverage_mean":.99,"missing_cells":int(sum(pd.isna(values)))}},
        "raster_metadata":[{"name":column,
                           "data_year":expected[2],
                           "data_source":expected[1],
                           "path":"fixture.tif","crs":"ESRI:54009","band":1}],
    }))
    return path


def test_local_static_wide_reuses_2020_built_and_multiple_native_sources(tmp_path):
    grid,base=fixture(tmp_path)
    hand=local(tmp_path,"hand","hand_m",[1.2,3.2,2.5])
    upa=local(tmp_path,"upa","upstream_area_km2",[20,200,30])
    hist=local(tmp_path,"hist","built_fraction_2000",[.1,.3,.2])
    result=fig2_static_local.assemble(
        tmp_path,grid,"fig2_static_combine_fixture",base,[hand,upa,hist])
    assert result["frozen_grid_count"]==3
    assert result["n_grids_missing_at_least_one_required"]==3
    folder=tmp_path/"data"/"derived"/"fig2_static_combine_fixture"
    x=pd.read_parquet(folder/"fig2_GF10_local_static_wide.parquet")
    assert len(x)==3
    assert x.built_fraction_2020.tolist()==[.25,.65,.35]
    assert x.built_growth_2000_2020.tolist()==pytest.approx([.15,.35,.15])
    assert x.hand_m.tolist()==pytest.approx([1.2,3.2,2.5])
    assert "rain_24h_mm" not in x.columns
    assert not np.isfinite(pd.to_numeric(x["built_growth_2000_2020"])).any()==False
    dictionary=pd.read_csv(folder/"fig2_static_indicator_dictionary.csv")
    assert dictionary.loc[dictionary.indicator.eq("vegetation_fraction"),
                          "source_epoch"].iloc[0]==2021
    assert dictionary.loc[dictionary.indicator.eq("hand_m"),
                          "temporal_type"].iloc[0]=="static"
    assert (folder/"fig2_GF10_required_missing_by_grid.parquet").is_file()
    # Reuse new STATIC QC as preferred local source in existing GEE gap-only path.
    r=merge_sources(tmp_path,grid,"fig2_static_bridge_fixture",
                    local_static=folder/"fig2_GF10_local_static_wide.parquet")
    assert r["frozen_grid_count"]==3
    assert not r["gee_tasks_submitted"]
    with pytest.raises(FileExistsError):
        fig2_static_local.assemble(tmp_path,grid,"fig2_static_combine_fixture",base,
                                   [hand,upa,hist])


def test_local_conflicting_2020_ghsl_is_fail_closed(tmp_path):
    grid,base=fixture(tmp_path)
    conflict=local(tmp_path,"conflict","built_fraction_2020",[.9,.65,.35])
    with pytest.raises(ValueError,match="local source conflicts"):
        fig2_static_local.assemble(tmp_path,grid,"fig2_static_conflict_fixture",
                                   base,[conflict])


def test_local_low_coverage_wrong_year_and_fake_annual_data_rejected(tmp_path):
    grid,base=fixture(tmp_path)
    bad=local(tmp_path,"lowcov","hand_m",[1.,2.,3.],[.99,.80,.99])
    with pytest.raises(ValueError,match="insufficient native coverage"):
        fig2_static_local.assemble(tmp_path,grid,"fig2_static_bad_cov",base,[bad])
    year=local(tmp_path,"wrongyear","built_fraction_2000",[.1,.3,.2])
    audit=year.parent/"fig2_local_exact_qc.json"
    obj=json.loads(audit.read_text())
    obj["raster_metadata"][0]["data_year"]="2020"
    audit.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match="incompatible epoch"):
        fig2_static_local.assemble(tmp_path,grid,"fig2_static_bad_year",base,[year])
    wrong=base/"bad.parquet"
    pd.DataFrame({"grid_id":["0_0"],"annual_rain_2024_mm":[100]}).to_parquet(wrong)
    with pytest.raises(ValueError,match="No recognized static"):
        fig2_static_local.assemble(tmp_path,grid,"fig2_static_bad_fields",wrong,[])
