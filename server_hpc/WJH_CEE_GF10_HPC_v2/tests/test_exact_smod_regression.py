import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box
from exactextract import exact_extract

from gf10hpc.exact import _exact_one
from gf10hpc.raster import PROFILES


def test_exactextract_pandas_unique_frac_not_frac_as_map(tmp_path):
    """Regression: in exactextract 0.3, PandasWriter does not support map_fields."""
    source = tmp_path / "GHS_SMOD_E2020_1km.tif"
    a = np.array([[21, 30], [23, 30]], dtype=np.int16)
    with rasterio.open(
        source, "w", driver="GTiff", height=2, width=2, count=1,
        dtype="int16", crs="ESRI:54009",
        transform=from_origin(0, 2000, 1000, 1000), nodata=-200
    ) as ds:
        ds.write(a, 1)
    zones = gpd.GeoDataFrame(
        {"grid_id": ["0_0"]}, geometry=[box(0, 0, 2000, 2000)],
        crs="ESRI:54009"
    )
    extracted = exact_extract(
        source, zones, ["count", "unique", "frac"],
        include_cols=["grid_id"], output="pandas"
    )
    assert len(extracted) == 1
    observed = dict(zip(
        np.asarray(extracted["unique"].iloc[0]).tolist(),
        np.asarray(extracted["frac"].iloc[0]).tolist()
    ))
    assert observed[21] == 0.25
    assert observed[23] == 0.25
    assert observed[30] == 0.5


def test_native_smod_classes_actual_tile(tmp_path):
    """Run actual C++ native raster against original EPSG6933 GF10 geometry."""
    source = tmp_path / "GHS_SMOD_E2020_1km.tif"
    a = np.array([[21, 30], [23, 30]], dtype=np.int16)
    with rasterio.open(
        source, "w", driver="GTiff", height=2, width=2, count=1,
        dtype="int16", crs="ESRI:54009",
        transform=from_origin(0, 2000, 1000, 1000), nodata=-200
    ) as ds:
        ds.write(a, 1)
    tile = tmp_path / "tile_00000_00000.parquet"
    pd.DataFrame([{
        "grid_id": "0_0", "grid_x": 0, "grid_y": 0,
        "land_area_km2": 100.0
    }]).to_parquet(tile, index=False)
    result = _exact_one((
        str(tile), 0, 0, 16, [str(source)],
        PROFILES["ghsl_smod_2020"], str(tmp_path / "out"), "fixed-job"
    ))
    assert result["status"] == "WROTE"
    output = pd.read_parquet(tmp_path / "out" / "tiles" / tile.name)
    cols = [f"smod_2020_class_{c}_full_cell_fraction" for c in (21, 23, 30)]
    assert output[cols].notna().all().all()
    assert (output[cols].to_numpy() >= 0).all()
    assert (output[cols].to_numpy() <= 1).all()
    assert output[cols].to_numpy().sum() > 0
    assert np.isfinite(output["smod_urban_fraction_2020_full_cell"].iloc[0])
