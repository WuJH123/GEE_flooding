"""Generate a bounded true-land geometry from GSHHG Full L1-L4.

Source 2026-11-04 Gate C used (L1-L2+L3-L4) in EPSG6933. We never
substitute a cell's land_area scalar for actual polygon intersection.
"""
from __future__ import annotations
from pathlib import Path
import json

def discover_gshhg(root):
    root=Path(root)
    names={f'GSHHS_f_L{i}.shp':None for i in (1,2,3,4)}
    candidates=[root/'data'/'raw',root/'data'/'reference',root/'data',root]
    for base in candidates:
        if not base.exists():continue
        for p in base.rglob('GSHHS_f_L1.shp'):
            sibling={k:p.with_name(k) for k in names}
            if all(q.exists() for q in sibling.values()):return sibling
    raise FileNotFoundError('GSHHG Full L1–L4 shapefiles not found; copy official GSHHG 2.3.7 source. No full-cell fallback is allowed.')

def prepare_land_tile(gshhg_paths, bbox_6933, expected_land_km2=None):
    """Clip GSHHG to tile, remove lakes and re-add islands; return WGS84 GeoJSON.

    Grid-edge densification preserves nonlinear EPSG6933->WGS84 bbox. Reject
    antimeridian ambiguity rather than silently dropping coastlines.
    """
    import geopandas as gpd
    from shapely.geometry import box,mapping
    from shapely import transform as geom_transform
    from shapely.ops import unary_union
    from pyproj import Transformer
    from shapely.validation import make_valid
    import numpy as np
    from .grid import tile_bounds
    b=box(*bbox_6933)
    to_ll=Transformer.from_crs(6933,4326,always_xy=True)
    to_eq=Transformer.from_crs(4326,6933,always_xy=True)
    x0,y0,x1,y1=b.bounds
    # Dense boundary prevents under-inclusive longitude/latitude clipping.
    xs=np.linspace(x0,x1,33); ys=np.linspace(y0,y1,33)
    coords=[(x,y0) for x in xs]+[(x,y1) for x in xs]+[(x0,y) for y in ys]+[(x1,y) for y in ys]
    ll=[to_ll.transform(x,y) for x,y in coords]
    lngs=[p[0] for p in ll]; lats=[p[1] for p in ll]
    if max(lngs)-min(lngs)>175:raise ValueError('Antimeridian/polar geometry requires separate audited source tile')
    lonlat_bbox=(min(lngs)-0.05,min(lats)-0.05,max(lngs)+0.05,max(lats)+0.05)
    parts=[]
    for i in (1,2,3,4):
        src=gshhg_paths[f'GSHHS_f_L{i}.shp']
        g=gpd.read_file(src,bbox=lonlat_bbox)
        if g.empty:parts.append(None);continue
        if g.crs is None:raise ValueError(f'GSHHG L{i} missing CRS')
        geoms=[make_valid(geom) for geom in g.to_crs(epsg=6933).geometry if geom is not None and not geom.is_empty]
        parts.append(unary_union(geoms).intersection(b) if geoms else None)
    land=parts[0]
    if land is None or land.is_empty:return {'type':'GeometryCollection','geometries':[]},0.
    for i in (1,2,3):
        other=parts[i]
        if other is None or other.is_empty:continue
        land=land.difference(other) if i%2 else land.union(other)
    land=make_valid(land.intersection(b))
    area=land.area/1e6
    if expected_land_km2 is not None and abs(area-expected_land_km2)>max(0.03,0.002*expected_land_km2):
        raise ValueError(f'GSHHG area mass balance fails: {area:.6f} vs {expected_land_km2:.6f} km2')
    if land.is_empty:return {'type':'GeometryCollection','geometries':[]},0.
    # Avoid automatically simplifying full-resolution source geometry.
    geom_ll=geom_transform(land,to_ll.transform,interleaved=False)
    result=mapping(geom_ll)
    return result,float(area)
