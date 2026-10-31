"""Read-only GISD30 tile coverage audit for frozen GF10 cells.

This does NOT compute impervious area. It identifies source TIFF coverage
using actual raster bounds, not filenames, to prioritize *only* locally missing
Zenodo geographic tiles. No downloads or archive modification.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
from shapely.geometry import box, Polygon
from .fig2_gee import wgs84_ring
from .paths import safe_output,atomic_json


def audit(root,grid,candidates,tag="fig2_gisd30_tile_audit_v1"):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use immutable fig2_* report version")
    d=pd.read_parquet(grid)
    need={"grid_id","grid_x","grid_y"}
    if need-set(d):raise ValueError("Frozen GF10 missing required coordinates")
    if d.grid_id.duplicated().any():raise ValueError("Duplicate GF10 ids")
    candidates=pd.read_csv(candidates)
    if "path" not in candidates:raise ValueError("Candidate inventory must contain full path column")
    matches=candidates.loc[
        candidates.path.astype(str).str.contains("GISD30",case=False,regex=False)
        & candidates.path.astype(str).str.lower().str.endswith((".tif",".tiff"))].copy()
    matches=matches.drop_duplicates("path")
    import rasterio
    tiles=[]
    for filename in matches.path:
        p=Path(filename)
        if not p.is_file():continue
        with rasterio.open(p) as src:
            if src.count!=1 or src.crs is None or str(src.crs).upper()!="EPSG:4326":
                continue
            t=src.bounds
            tiles.append((str(p),box(t.left,t.bottom,t.right,t.top)))
    coverage=[]
    for row in d.itertuples(index=False):
        geom=Polygon(wgs84_ring(row.grid_x,row.grid_y,steps=16))
        found=[name for name,region in tiles if region.intersects(geom)]
        coverage.append(dict(grid_id=str(row.grid_id),
                             n_overlapping_local_tifs=len(found),
                             local_tif_candidates=";".join(found),
                             requires_GISD30_source_tile=not bool(found),
                             warning="Tile overlap only; pixel values and 10km valid area NOT checked"))
    results=pd.DataFrame(coverage)
    out=safe_output(root,"reports/"+tag)
    if out.exists():raise FileExistsError(str(out))
    out.mkdir(parents=True,exist_ok=False)
    results.to_csv(out/"fig2_gisd30_frozen_grid_tile_coverage.csv",index=False)
    qc=dict(status="GISD30_LOCAL_METADATA_ONLY",
            frozen_GF10_count=len(d),
            candidate_geographic_tif_count=len(tiles),
            GF10_with_candidate_tile=int((results.n_overlapping_local_tifs>0).sum()),
            GF10_without_candidate_tile=int(results.requires_GISD30_source_tile.sum()),
            data_pixels_read=False,no_downloads=True,
            known_source="https://zenodo.org/records/5220816",
            caveat="GISD30 class 0 is pervious; 1-8 are impervious epochs by 2020. 5-degree source tile overlap is not measured coverage.")
    atomic_json(out/"fig2_gisd30_tile_coverage_qc.json",qc)
    return qc

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--candidates",type=Path,required=True)
    p.add_argument("--tag",default="fig2_gisd30_tile_audit_v1")
    a=p.parse_args(argv)
    print(json.dumps(audit(a.root,a.grid,a.candidates,a.tag),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
