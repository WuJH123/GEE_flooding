import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from gee_flooding import fig2_gisd30_coverage


def test_geographic_GISD30_tiles_are_discovery_not_fake_fractions(tmp_path):
    grid=tmp_path/"grid.parquet"
    pd.DataFrame({"grid_id":["0_0","1_0"],"grid_x":[0,1],"grid_y":[0,0]}).to_parquet(grid)
    tif=tmp_path/"GISD30_1985-2020_E0N0.tif"
    with rasterio.open(tif,"w",driver="GTiff",crs="EPSG:4326",
                       width=10,height=10,count=1,dtype="uint8",
                       transform=from_origin(0,.1,.005,.01)) as ds:
        ds.write(np.ones((10,10),dtype="uint8"),1)
    index=tmp_path/"candidates.csv"
    pd.DataFrame({"path":[str(tif),str(tmp_path/"a.rar")]}).to_csv(index,index=False)
    q=fig2_gisd30_coverage.audit(tmp_path,grid,index,tag="fig2_gisd_tiles_fixture")
    assert q["frozen_GF10_count"]==2
    assert q["GF10_with_candidate_tile"]==1
    assert q["GF10_without_candidate_tile"]==1
    assert q["data_pixels_read"] is False
    report=pd.read_csv(tmp_path/"reports"/"fig2_gisd_tiles_fixture"/
                       "fig2_gisd30_frozen_grid_tile_coverage.csv")
    assert report.loc[report.grid_id.eq("0_0"),"requires_GISD30_source_tile"].iloc[0]==False
    assert report.loc[report.grid_id.eq("1_0"),"requires_GISD30_source_tile"].iloc[0]==True
