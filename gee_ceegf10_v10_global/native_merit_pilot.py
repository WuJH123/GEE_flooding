"""New source-native GEE MERIT zonal pilot, never mixed with frozen V7/V8 data.

This tests a scientific method change needed above the 65,536 native-pixel
reduceResolution cap. A real export plus independent native-pixel QC must pass
before any global native-zonal task is planned or submitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import ee
import pandas as pd


ROOT = Path(r"E:\GEE_flooding")
HERE = ROOT / "CEE_GF10_COST_OPT_V10_20261106"
GRID = ROOT / "gee_ceegf10_v1" / "gf10_global_nonantarctic_land.parquet"
PROJECT = "future-shuttle-513705-g9"
GF10_SHA = "4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d"
SITES = {"wuhan": {"x": (1080, 1119), "y": (350, 379), "count": 1000},
         "greenland": {"x": (-500, -301), "y": (723, 729), "count": 300},
         "wuhan_join": {"x": (1080, 1119), "y": (350, 379), "count": 1000},
         "greenland_join": {"x": (-500, -301), "y": (723, 729), "count": 300},
         "westedge_join": {"x": (-1720, -1711), "y": (670, 679), "count": 100},
         "wuhan_weighted": {"x": (1080, 1119), "y": (350, 379), "count": 1000},
         "greenland_weighted": {"x": (-500, -301), "y": (723, 729), "count": 300},
         "westedge_weighted": {"x": (-1720, -1711), "y": (670, 679), "count": 100}}
MEAN_NAMES = ["merit_hand_mean_m", "merit_elv_mean_m", "merit_upa_mean_km2",
              "merit_permanent_water_fraction", "merit_valid_fraction",
              "merit_hand_le2_fraction_valid", "merit_hand_le5_fraction_valid",
              "merit_hand_le10_fraction_valid", "merit_slope_mean_deg",
              "merit_slope_le2_fraction_valid"]
SELECTORS = ["grid_id"] + MEAN_NAMES + ["hnd_p10", "hnd_p50", "hnd_p90", "upa_max", "upa_p90"]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source(site: str) -> pd.DataFrame:
    if sha(GRID) != GF10_SHA:
        raise ValueError("Frozen GF10 file changed")
    box = SITES[site]
    frame = pd.read_parquet(GRID, columns=["grid_id", "grid_x", "grid_y", "latitude"])
    frame = frame.loc[frame.grid_x.between(*box["x"]) & frame.grid_y.between(*box["y"])].copy()
    frame = frame.sort_values(["grid_y", "grid_x"]).head(box["count"])
    if len(frame) != box["count"] or frame.grid_id.duplicated().any():
        raise ValueError("Native MERIT pilot GF10 sample invalid")
    return frame


def output_paths(site: str) -> tuple[Path, Path, Path, str]:
    name = f"CEE_GF10_MERIT_NATIVE_V10_{site.upper()}_{SITES[site]['count']}"
    directory = HERE / "native_merit_pilots" / site
    return directory, directory / "input.parquet", directory / "intent.json", name


def build(ee, site: str, frame: pd.DataFrame):
    wkt = json.loads((ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105" /
                      "config" / "recovery.json").read_text(encoding="utf-8"))["crs_wkt"]
    features = []
    for row in frame.itertuples(index=False):
        x, y = int(row.grid_x), int(row.grid_y)
        geom = ee.Geometry.Rectangle([x * 10000, y * 10000, (x + 1) * 10000,
                                      (y + 1) * 10000], proj=wkt, geodesic=False)
        features.append(ee.Feature(geom, {"grid_id": str(row.grid_id)}))
    fc = ee.FeatureCollection(features)
    src = ee.Image("MERIT/Hydro/v1_0_1")
    hnd, upa = src.select("hnd"), src.select("upa")
    slope = ee.Terrain.slope(src.select("elv"))
    stats = ee.Image.cat([hnd, src.select("elv"), upa, src.select("wat").eq(1),
                          hnd.mask().unmask(0), hnd.lte(2), hnd.lte(5),
                          hnd.lte(10), slope, slope.lte(2)]).rename(MEAN_NAMES)
    # Native source projection and region geometry avoid both the explicit
    # 500m reprojection and per-output-pixel reduceResolution ceiling.
    weighted_method = site.endswith("_weighted")
    if weighted_method:
        # Native EPSG:4326 pixel area varies strongly within polar GF10. An
        # unweighted native mean biased Greenland UPA by 1.64% against exact
        # source pixels. Sum value*pixelArea / sum(pixelArea) for each band.
        area = ee.Image.pixelArea()
        numerator_denominator = []
        for name, source_band in zip(MEAN_NAMES, [
                hnd, src.select("elv"), upa, src.select("wat").eq(1),
                hnd.mask().unmask(0), hnd.lte(2), hnd.lte(5),
                hnd.lte(10), slope, slope.lte(2)]):
            numerator_denominator.extend([
                source_band.multiply(area).rename(name + "_num"),
                area.updateMask(source_band.mask()).rename(name + "_den")])
        sums = ee.Image.cat(numerator_denominator).reduceRegions(
            collection=fc, reducer=ee.Reducer.sum(), crs=hnd.projection(),
            tileScale=8, maxPixelsPerRegion=2500000)
        def to_means(feature):
            feature = ee.Feature(feature)
            for name in MEAN_NAMES:
                denominator = feature.get(name + "_den")
                value = ee.Algorithms.If(denominator,
                                         ee.Number(feature.get(name + "_num")).divide(
                                             ee.Number(denominator)), None)
                feature = feature.set(name, value)
            return feature
        base = sums.map(to_means)
    else:
        # The native source bbox for every frozen high-latitude GF10 is <=103,125
        # pixels. The ten-band reducer can account for up to 10x that count.
        base = stats.reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                   crs=hnd.projection(), tileScale=8,
                                   maxPixelsPerRegion=1200000)
    reducer = ee.Reducer.percentile([10, 50, 90], maxRaw=150000).combine(
        ee.Reducer.max(), sharedInputs=True)
    percent = ee.Image.cat([hnd, upa]).reduceRegions(
        collection=fc, reducer=reducer, crs=hnd.projection(),
        tileScale=8, maxPixelsPerRegion=250000)
    # Nested reduceRegions(base) caused an EE zero-error-margin geometry
    # failure on valid west-edge GF10. Independent source reductions joined on
    # the frozen grid_id passed west-edge, interior and high-lat interactive QC.
    joined = ee.Join.inner().apply(
        base, percent, ee.Filter.equals(leftField="grid_id", rightField="grid_id"))
    def collapse(pair):
        left = ee.Feature(pair.get("primary"))
        right = ee.Feature(pair.get("secondary"))
        return ee.Feature(None, left.toDictionary().combine(right.toDictionary(), True))
    return ee.FeatureCollection(joined.map(collapse))


def main(site: str, execute: bool) -> None:
    frame = source(site)
    directory, input_file, intent_file, name = output_paths(site)
    if not execute:
        print(json.dumps({"status": "DRY_RUN_NO_GEE_SUBMISSION", "site": site,
                          "n_GF10": len(frame), "latitude_range": [float(frame.latitude.min()),
                                                               float(frame.latitude.max())],
                          "name": name, "source": "MERIT/Hydro/v1_0_1",
              "maxRaw": 150000, "independent_reducer_join": True,
              "area_weighted_means": site.endswith("_weighted"),
              "native_region_science_QC_pending": True}))
        return
    if intent_file.exists():
        raise RuntimeError("Existing pilot intent; no duplicate submission")
    ee.Initialize(project=PROJECT)
    if any(x.get("description") == name for x in ee.data.getTaskList()):
        raise RuntimeError("Pilot description already exists in GEE")
    product = build(ee, site, frame)
    task = ee.batch.Export.table.toDrive(
        collection=product, description=name,
        folder="CEE_GF10_MERIT_NATIVE_V10_20261106", fileNamePrefix=name,
        fileFormat="CSV", selectors=SELECTORS)
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(input_file, index=False)
    intent = {"state": "SUBMISSION_INTENT", "name": name, "project": PROJECT,
              "grid_sha256": GF10_SHA, "input_sha256": sha(input_file),
              "n_GF10": len(frame), "science_method": (
                  "NATIVE_PIXEL_AREA_WEIGHTED_JOIN_MAXRAW_150000" if site.endswith("_weighted")
                  else "NATIVE_JOIN_BY_GF10_MAXRAW_150000"),
              "globally_approved": False}
    intent_file.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    task.start()
    intent.update(state="SUBMITTED_NOT_QC", task_id=task.id)
    intent_file.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    print(json.dumps({"state": "SUBMITTED_NOT_QC", "site": site,
                      "task_id": task.id, "name": name}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=sorted(SITES), required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    main(args.site, args.execute)
