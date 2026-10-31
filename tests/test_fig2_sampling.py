import pandas as pd
import pytest
from gee_flooding.fig2_sampling import sample


def test_geographic_design_uses_unchanged_GF10_ids(tmp_path):
    cells=[]
    citymap=[]
    metadata=[]
    for i in range(8):
        cid=f"UC{i}"
        metadata.append(dict(city_id=cid,continent="Asia" if i%2==0 else "Europe",
                             koppen_broad=f"climate{i%3}"))
        for j in range(3):
            x=i*3+j
            gid=f"{x}_0"
            cells.append(dict(grid_id=gid,grid_x=x,grid_y=0,urban_fraction_2020=.4))
            citymap.append(dict(grid_id=gid,city_id=cid))
    p=tmp_path/"grid.parquet";q=tmp_path/"cities.parquet";z=tmp_path/"meta.csv"
    pd.DataFrame(cells).to_parquet(p,index=False)
    pd.DataFrame(citymap).to_parquet(q,index=False)
    pd.DataFrame(metadata).to_csv(z,index=False)
    a,qa=sample(p,q,z,max_cities=6,cells_per_city=2)
    b,qb=sample(p,q,z,max_cities=6,cells_per_city=2)
    assert a.grid_id.tolist()==b.grid_id.tolist()
    assert len(a)==12
    assert qa["independent_of_news_labels"] is True
    assert set(a.grid_id)<=set(pd.DataFrame(cells).grid_id)
    assert (a.grid_id.str.split("_").str[0].astype(int)==a.grid_x).all()


def test_sample_rejects_illegal_configuration(tmp_path):
    with pytest.raises(ValueError):
        sample(None,None,None,max_cities=0)


def test_frozen_sampling_includes_preselected_development_train_and_heldout(tmp_path):
    grid=[]; crosswalk=[]; meta=[]; v3=[]
    for i in range(12):
        city=f"UC{i}"
        flag="TRAIN_CANDIDATE" if i<8 else "HELDOUT_CITY_CANDIDATE"
        meta.append(dict(city_id=city,continent="Asia" if i%2 else "Europe",
                         koppen_broad="A" if i%3 else "B"))
        v3.append(dict(city_id=city,fig1_v3_status=flag,
                       eligible_using_only_development_years=True))
        for j in range(2):
            x=i*2+j
            grid.append(dict(grid_id=f"{x}_0",grid_x=x,grid_y=0,urban_fraction_2020=.7))
            crosswalk.append(dict(grid_id=f"{x}_0",city_id=city))
    g=tmp_path/"frozen.parquet";x=tmp_path/"crosswalk.parquet"
    c=tmp_path/"cities.csv";audit=tmp_path/"fig1v3.csv"
    pd.DataFrame(grid).to_parquet(g,index=False)
    pd.DataFrame(crosswalk).to_parquet(x,index=False)
    pd.DataFrame(meta).to_csv(c,index=False)
    pd.DataFrame(v3).to_csv(audit,index=False)
    selected,qc=sample(g,x,c,max_cities=10,cells_per_city=2,
                       seed=42,frozen_v3=audit)
    assert qc["frozen_train_cities"]>=3
    assert qc["frozen_heldout_cities"]>=2
    assert not qc["independent_of_news_labels"]
    assert qc["independent_of_2024_2025_news"]
    assert qc["used_2021_2023_reporting_eligibility"]
    assert selected.grid_id.is_unique
