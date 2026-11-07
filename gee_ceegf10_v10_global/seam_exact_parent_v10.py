"""Recover one antimeridian parent from GEE native pixels with exact GF10 overlap.

GEE computes source pixels and slope; local arithmetic only calculates precise
intersections of native pixel footprints with the frozen EPSG:6933 cell. This
avoids the demonstrated geometry error in GEE's seam reduceRegion operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from pyproj import Transformer

from seam_exact_source_one_cell import weighted_percentile

ROOT = Path(r"E:\GEE_flooding")
HERE = Path(__file__).resolve().parent
GRID = ROOT / "gee_ceegf10_v1/gf10_global_nonantarctic_land.parquet"
QUARANTINE = ROOT / "CEE_GF10_GEE_RECOVERY_V4_20261105/plans/merit_quarantine_v4.csv"
OUT = HERE / "merit_seam_exact_parents"
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core, eeops  # noqa: E402


def read_parent(key: str) -> pd.DataFrame:
    if core.sha(GRID) != core.GRID_SHA:
        raise ValueError("Frozen GF10 SHA-256 mismatch")
    quarantine = pd.read_csv(QUARANTINE)
    row = quarantine.loc[quarantine.tile_key.eq(key)]
    if len(quarantine) != 14 or len(row) != 1 or int(quarantine.n_land_cells.sum()) != 450:
        raise ValueError("Parent is not one of the 14 immutable seam blocks")
    grid = pd.read_parquet(GRID, columns=["grid_id", "grid_x", "grid_y", "land_area_km2"])
    parts = key.split("_")
    x0, y0 = int(parts[1]), int(parts[2])
    cells = grid.loc[grid.grid_x.between(x0, x0+9) &
                     grid.grid_y.between(y0, y0+9)].copy()
    if len(cells) != int(row.iloc[0].n_land_cells) or cells.grid_id.duplicated().any():
        raise ValueError("Seam parent frozen GF10 member mismatch")
    return cells.sort_values("grid_id")


def source_group(ee_module, boxes: list[list[float]], source,
                 forward, inverse, transform) -> dict:
    sx, _, tx, _, sy, ty = transform
    xa, ya = min(b[0] for b in boxes), min(b[1] for b in boxes)
    xb, yb = max(b[2] for b in boxes), max(b[3] for b in boxes)
    lon0, lat0 = forward.transform(xa, ya)
    lon1, lat1 = forward.transform(xb, yb)
    if not (math.isfinite(lon0) and math.isfinite(lon1) and lon0 < lon1 and lat0 < lat1):
        raise ValueError("Seam native source group crosses longitude discontinuity")
    c0, c1 = math.floor((lon0-tx)/sx)-1, math.ceil((lon1-tx)/sx)+1
    r0, r1 = math.floor((lat1-ty)/sy)-1, math.ceil((lat0-ty)/sy)+1
    width, height = c1-c0, r1-r0
    if not (0 < width*height <= 2500000):
        raise ValueError("Seam source request exceeds 2.5 million native pixels")
    request_grid = {"dimensions": {"width": width, "height": height},
                    "affineTransform": {"scaleX": sx, "shearX": 0,
                                        "translateX": tx+c0*sx,
                                        "shearY": 0, "scaleY": sy,
                                        "translateY": ty+r0*sy}, "crsCode": "EPSG:4326"}
    raw = ee_module.data.getPixels({"assetId": "MERIT/Hydro/v1_0_1",
                                    "fileFormat": "NUMPY_NDARRAY",
                                    "bandIds": ["hnd", "elv", "upa", "wat"],
                                    "grid": request_grid})
    slope = ee_module.Terrain.slope(source.select("elv")).rename("slope")
    gradient = ee_module.data.computePixels({
        "expression": ee_module.Image.cat([slope, slope.mask().rename("slope_mask")]),
        "fileFormat": "NUMPY_NDARRAY", "bandIds": ["slope", "slope_mask"],
        "grid": request_grid})
    lon_edges = tx + np.arange(c0, c1+1)*sx
    lat_edges = ty + np.arange(r0, r1+1)*sy
    px, _ = inverse.transform(lon_edges, np.zeros_like(lon_edges))
    _, py = inverse.transform(np.zeros_like(lat_edges), lat_edges)
    fingerprint = hashlib.sha256(raw.tobytes()+gradient.tobytes()).hexdigest()
    return {"raw": raw, "gradient": gradient, "px": px, "py": py,
            "source_shape": [height, width], "source_pixel_SHA256": fingerprint,
            "source_grid": request_grid, "bounds": [xa, ya, xb, yb]}


def one_from_groups(gid: str, groups: dict[str, dict]) -> tuple[dict, dict]:
    x, y = map(int, gid.split("_"))
    part_arrays = []
    total_intersecting = 0
    for xa, ya, xb, yb in eeops.projected_seam_segments(x, y):
        group = groups["east" if xa >= 0 else "west"]
        px, py = group["px"], group["py"]
        wx = np.maximum(0, np.minimum(px[1:],xb)-np.maximum(px[:-1],xa))
        wy = np.maximum(0, np.minimum(py[:-1],yb)-np.maximum(py[1:],ya))
        cols, rows = np.flatnonzero(wx > 0), np.flatnonzero(wy > 0)
        if not len(cols) or not len(rows):
            raise ValueError("Seam GF10 segment has zero source-pixel overlap")
        c0, c1 = cols[0], cols[-1]+1
        r0, r1 = rows[0], rows[-1]+1
        weights = wy[r0:r1,None]*wx[None,c0:c1]
        raw = group["raw"][r0:r1,c0:c1]
        gradient = group["gradient"][r0:r1,c0:c1]
        total_intersecting += int((weights > 0).sum())
        part_arrays.append((weights, raw, gradient))
    def collect(name, hand_mask=False):
        values, weights = [], []
        for w, raw, grad in part_arrays:
            if name == "slope":
                a = np.asarray(grad["slope"], dtype=float)
                mask = np.asarray(grad["slope_mask"], dtype=float) > 0
            else:
                a = np.asarray(raw[name], dtype=float)
                if hand_mask:
                    h = np.asarray(raw["hnd"], dtype=float)
                    mask = np.isfinite(h) & (h > -9990)
                else:
                    mask = np.isfinite(a) & (a > -9990)
            keep = (w > 0) & mask
            values.append(a[keep])
            weights.append(w[keep])
        return np.concatenate(values), np.concatenate(weights)
    def mean(name):
        v, w = collect(name)
        return float(np.average(v,weights=w)) if len(v) else None
    hnd, wh = collect("hnd")
    upa, wu = collect("upa")
    water, ww = collect("wat", True)
    slope, ws = collect("slope")
    if len(water) != len(hnd) or not np.array_equal(wh,ww):
        raise ValueError("MERIT HND/WAT native source overlap mismatch")
    if wh.sum() > 100000000.01:
        raise ValueError("Source overlap exceeds original GF10 area")
    metrics = {
        "merit_hand_mean_m": mean("hnd"),
        "merit_elv_mean_m": mean("elv"),
        "merit_upa_mean_km2": mean("upa"),
        "merit_permanent_water_fraction": float(np.average(water==1,weights=ww)) if len(water) else None,
        "merit_valid_fraction": float(wh.sum()/100000000),
        "merit_hand_le2_fraction_valid": float(np.average(hnd<=2,weights=wh)) if len(hnd) else None,
        "merit_hand_le5_fraction_valid": float(np.average(hnd<=5,weights=wh)) if len(hnd) else None,
        "merit_hand_le10_fraction_valid": float(np.average(hnd<=10,weights=wh)) if len(hnd) else None,
        "merit_slope_mean_deg": float(np.average(slope,weights=ws)) if len(slope) else None,
        "merit_slope_le2_fraction_valid": float(np.average(slope<=2,weights=ws)) if len(slope) else None,
        "merit_upa_max_km2": float(upa.max()) if len(upa) else None,
        "merit_upa_max_log1p": math.log1p(max(0,float(upa.max()))) if len(upa) else None,
        "merit_hand_p10_m": weighted_percentile(hnd,wh,10),
        "merit_hand_p50_m": weighted_percentile(hnd,wh,50),
        "merit_hand_p90_m": weighted_percentile(hnd,wh,90),
        "merit_upa_p90_km2": weighted_percentile(upa,wu,90),
    }
    if set(metrics) != set(core.BANDS):
        raise ValueError("MERIT 16-band contract changed")
    return metrics, {"source_valid_area_km2": float(wh.sum()/1e6),
                     "source_intersection_pixels": total_intersecting,
                     "segment_count": len(part_arrays)}


def validate(frame: pd.DataFrame) -> dict:
    fractions = ["merit_permanent_water_fraction", "merit_valid_fraction",
                 "merit_hand_le2_fraction_valid", "merit_hand_le5_fraction_valid",
                 "merit_hand_le10_fraction_valid", "merit_slope_le2_fraction_valid"]
    for name in fractions:
        if not frame[name].dropna().between(-1e-6,1.000001).all():
            raise ValueError("Seam source fraction outside physical range: " + name)
    observed = frame.merit_valid_fraction.fillna(0) > 0
    if not (frame.loc[observed,"merit_hand_le2_fraction_valid"] <=
            frame.loc[observed,"merit_hand_le5_fraction_valid"] + 1e-6).all():
        raise ValueError("Seam HAND threshold nonnested")
    if not (frame.loc[observed,"merit_hand_le5_fraction_valid"] <=
            frame.loc[observed,"merit_hand_le10_fraction_valid"] + 1e-6).all():
        raise ValueError("Seam HAND threshold nonnested")
    if not (frame.loc[observed,"merit_hand_p10_m"] <= frame.loc[observed,"merit_hand_p50_m"]).all():
        raise ValueError("Seam HAND p10>p50")
    if not (frame.loc[observed,"merit_hand_p50_m"] <= frame.loc[observed,"merit_hand_p90_m"]).all():
        raise ValueError("Seam HAND p50>p90")
    if not (frame.merit_upa_p90_km2.dropna() <=
            frame.loc[frame.merit_upa_p90_km2.notna(),"merit_upa_max_km2"] + 1e-4).all():
        raise ValueError("Seam UPA p90>max")
    if not frame.merit_slope_mean_deg.dropna().between(0,90.0001).all():
        raise ValueError("Seam slope degree range invalid")
    if not np.allclose(frame.merit_upa_max_log1p.dropna(),
                       np.log1p(frame.loc[frame.merit_upa_max_log1p.notna(),
                                         "merit_upa_max_km2"].clip(lower=0)),
                       rtol=1e-8, atol=1e-8):
        raise ValueError("Seam UPA log1p identity failed")
    return {"source_gap_GF10": int((~observed).sum()),
            "missing_per_band": {name: int(frame[name].isna().sum()) for name in core.BANDS}}


def run(key: str) -> dict:
    cells = read_parent(key)
    target = OUT / key
    if (target / "audit.json").exists() or (target / "merit_source_candidate.parquet").exists():
        raise RuntimeError("Existing seam parent result; never overwrite without explicit reconciliation")
    ee.Initialize(project=core.PROJECT)
    source = ee.Image("MERIT/Hydro/v1_0_1")
    transform = source.select("hnd").projection().getInfo()["transform"]
    forward = Transformer.from_crs(6933,4326,always_xy=True)
    inverse = Transformer.from_crs(4326,6933,always_xy=True)
    boxes = {"west": [], "east": []}
    for gid in cells.grid_id:
        x,y = map(int,gid.split("_"))
        for box in eeops.projected_seam_segments(x,y):
            boxes["east" if box[0]>=0 else "west"].append(box)
    groups = {side: source_group(ee,box,source,forward,inverse,transform)
              for side,box in boxes.items() if box}
    values, diagnostics = [], []
    for gid in cells.grid_id:
        metrics, audit = one_from_groups(gid,groups)
        values.append({"grid_id": gid, **metrics})
        diagnostics.append({"grid_id": gid, **audit})
    frame = pd.DataFrame(values)
    if len(frame) != len(cells) or frame.grid_id.duplicated().any() or set(frame.grid_id)!=set(cells.grid_id):
        raise ValueError("Seam parent source GF10 conservation failed")
    physical = validate(frame)
    target.mkdir(parents=True,exist_ok=True)
    product = target / "merit_source_candidate.parquet"
    frame.to_parquet(product,index=False)
    report = {"status": "PARENT_EXACT_SOURCE_PIXEL_QC_PASS_GLOBAL_SEAM_APPROVAL_PENDING",
              "tile_key": key, "n_GF10": len(frame), "GF10_SHA256": core.GRID_SHA,
              "original_grid_ids_preserved": True,
              "source": "MERIT/Hydro/v1_0_1", "source_pixel_method": "GEE_NATIVE_PIXELS_EXACT_EPSG6933_OVERLAP",
              "source_groups": {name: {k:v for k,v in group.items() if k in
                                ("source_shape","source_pixel_SHA256","bounds")}
                                for name,group in groups.items()},
              "source_grid_diagnostics": diagnostics,
              "physical_QC": physical,
              "output_sha256": core.sha(product),
              "not_yet_counted_in_global_MERIT": True}
    core.write_json(target / "audit.json",report)
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tile-key",required=True)
    args=parser.parse_args()
    result=run(args.tile_key)
    print(json.dumps({k:v for k,v in result.items() if k not in
                      ("source_grid_diagnostics","source_groups")},indent=2))
