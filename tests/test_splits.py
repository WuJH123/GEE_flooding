import pandas as pd
from gee_flooding.train import city_storm_partition

def test_no_city_or_storm_leakage():
    df=pd.DataFrame([{'city_id':f'city_{i}','storm_id':f'storm_{j}'}
                     for i in range(20) for j in range(30) for _ in range(2)])
    train,test=city_storm_partition(df,42)
    assert len(train)>0 and len(test)>0
    assert not set(df.iloc[train].city_id)&set(df.iloc[test].city_id)
    assert not set(df.iloc[train].storm_id)&set(df.iloc[test].storm_id)
