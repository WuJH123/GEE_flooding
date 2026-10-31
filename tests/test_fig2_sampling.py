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
