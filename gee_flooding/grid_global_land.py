"""GF10 GLOBAL LAND v1: exact coastline-polygon × 10,000m equal-area grid.

Separate the immutable lattice from the 2020 GHSL urban eligibility mask.
GSHHG FULL resolution L1-L4 + Antarctic GROUNDING LINE L6 is required.
Any island actually represented as polygon in GSHHG is eligible even if
its GF10 centre is in the ocean. No >0 area cutoff; no raster centre test.

EPSG:6933 is officially valid only between 86S and 86N; use NSIDC
EASE 2.0 polar EPSG:6931/6932 outside these latitudes. Preserve pre-existing
EPSG6933 grid_id "x_y"; the distinct polar zones use N_x_y / S_x_y.
DO NOT pass polar cells to older EPSG6933-only fig2_gee exporters.

Only GSHHG shoreline source polygons are input; no user data is overwritten.
Outputs are immutable versioned Parquet shards + QCs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import transform
from shapely.prepared import prep
from shapely import make_valid
from .paths import safe_output, atomic_json

CELL=10000
CELL_AREA=float(CELL*CELL)
CAP=86.0
LEVEL_SIGNS={1:1,2:-1,3:1,4:-1,6:1}
ZONES={"G":(6933,-86,86),"N":(6931,86,90),"S":(6932,-90,-86)}
# 6933 projected bounds in official EPSG publication.
G_BOUNDS=(-17367530.45,-7324184.56,17367530.45,7324184.56)


def _fingerprint(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _polygons(geometry):
    if geometry.is_empty:return
    if isinstance(geometry,Polygon):
        yield geometry
    elif isinstance(geometry,(MultiPolygon,GeometryCollection)):
        for item in geometry.geoms:
            yield from _polygons(item)


def _iter_shapefile(path,batch=500):
    """Bounded source reader, even for GSHHG full-resolution islands."""
    import pyogrio
    # The shapefile supports ordinal feature slicing; avoid loading worldwide
    # full resolution coastal vertices all at once.
    info=pyogrio.read_info(path)
    if info.get("crs") not in ("EPSG:4326","OGC:CRS84"):
        raise ValueError("GSHHG must have original EPSG:4326 geography")
    total=int(info["features"])
    if total<1:raise ValueError("Empty coastline shapefile "+str(path))
    for offset in range(0,total,batch):
        small=pyogrio.read_dataframe(path,skip_features=offset,
                                     max_features=batch,columns=[])
        for shape in small.geometry:
            if shape is not None and not shape.is_empty:
                yield shape


def _split_dateline(g):
    """Normalize a polygon only when a ring actually crosses the date line.

    For ordinary GSHHG polygons bounded inside [-180,180], preserve their
    native geometry. For a >180-degree segment in a ring, unwrap longitude
    continuously then intersect 360-degree slabs before rewrapping. This
    keeps western Pacific islands from becoming world-spanning polygons.
    """
    def ring_needs_unwrap(coords):
        a=np.asarray(coords,float)
        return bool(len(a)>1 and np.any(np.abs(np.diff(a[:,0]))>180+1e-7))
    def unwrap(coords):
        a=np.asarray(coords,float)
        a[:,0]=np.rad2deg(np.unwrap(np.deg2rad(a[:,0]),discont=np.pi))
        return a
    for part in _polygons(g):
        cross=ring_needs_unwrap(part.exterior.coords) or any(
            ring_needs_unwrap(r.coords) for r in part.interiors)
        if not cross:
            yield part
            continue
        outer=unwrap(part.exterior.coords)
        holes=[unwrap(r.coords) for r in part.interiors]
        # Hole must belong in the same unwrap frame as exterior.
        middle=np.mean(outer[:,0])
        aligned=[]
        for hole in holes:
            k=round((middle-np.mean(hole[:,0]))/360)
            hole[:,0]+=k*360
            aligned.append(hole)
        unwrapped=Polygon(outer,aligned)
        if not unwrapped.is_valid:unwrapped=make_valid(unwrapped)
        for p in _polygons(unwrapped):
            left=math.floor(p.bounds[0]/360)
            right=math.ceil(p.bounds[2]/360)
            for shift in range(left-1,right+2):
                minx=-180+360*shift
                section=p.intersection(box(minx,-90, minx+360,90))
                if section.is_empty:continue
                for q in _polygons(section):
                    yield transform(lambda x,y,z=None:(np.asarray(x)-360*shift,y),q)


def _accumulate(poly,sign,areas,block=24):
    """Exact 10km intersection; acceleration for interior blocks/cells."""
    from shapely.geometry import box as cellbox
    if poly.is_empty:return
    if not poly.is_valid:poly=make_valid(poly)
    for part in _polygons(poly):
        if part.area<=0:continue
        q=prep(part)
        x0=math.floor(part.bounds[0]/CELL)
        y0=math.floor(part.bounds[1]/CELL)
        x1=math.ceil(part.bounds[2]/CELL)
        y1=math.ceil(part.bounds[3]/CELL)
        if (x1-x0)*(y1-y0)>4_000_000:
            raise ValueError("Projected polygon has implausibly global bounding box")
        for bx in range(x0,x1,block):
            for by in range(y0,y1,block):
                tx=min(bx+block,x1);ty=min(by+block,y1)
                tile=cellbox(bx*CELL,by*CELL,tx*CELL,ty*CELL)
                if not q.intersects(tile):continue
                if q.covers(tile):
                    for x in range(bx,tx):
                        for y in range(by,ty):
                            areas[x,y]+=sign*CELL_AREA
                    continue
                clip=part.intersection(tile)
                if clip.is_empty:continue
                clipped=prep(clip)
                ix0=max(bx,math.floor(clip.bounds[0]/CELL))
                iy0=max(by,math.floor(clip.bounds[1]/CELL))
                ix1=min(tx,math.ceil(clip.bounds[2]/CELL))
                iy1=min(ty,math.ceil(clip.bounds[3]/CELL))
                for x in range(ix0,ix1):
                    for y in range(iy0,iy1):
                        cell=cellbox(x*CELL,y*CELL,(x+1)*CELL,(y+1)*CELL)
                        if not clipped.intersects(cell):continue
                        a=CELL_AREA if clipped.covers(cell) else clip.intersection(cell).area
                        if a>0:areas[x,y]+=sign*a


def _zone_geometry(piece,zone,trans,lat_clip=None):
    epsg,lo,hi=ZONES[zone]
    clipped=piece.intersection(box(-180,lo,180,hi))
    if clipped.is_empty:return
    # At the 86th parallel polar projection needs curved boundary, not a
    # 180-degree chord. Segmentize only geographic edges >0.5 degrees.
    clipped=clipped.segmentize(.5)
    projected=transform(trans.transform,clipped)
    if zone=="G":
        projected=projected.intersection(box(*G_BOUNDS))
    if not projected.is_valid:projected=make_valid(projected)
    for poly in _polygons(projected):
        if poly.area>0:yield poly


def compute(source,resolution="f",subset=None,block=24):
    """Internal calculation. Output keyed by zone to prevent CRS collision.

    subset=(xmin,ymin,xmax,ymax) is for scientific smoke testing only,
    never a publishable global data product.
    """
    source=Path(source)
    if resolution not in ("f","h","i","l","c"):
        raise ValueError("Unknown GSHHG resolution")
    if block<4 or block>128:raise ValueError("Block size must be 4..128")
    if subset is not None:
        if len(subset)!=4 or not (-180<=subset[0]<subset[2]<=180 and
             -90<=subset[1]<subset[3]<=90):
            raise ValueError("Invalid WGS84 smoke-test geographic bbox")
        subset_poly=box(*subset)
    else:subset_poly=None
    origins={zone:Transformer.from_crs(4326,epsg,always_xy=True)
             for zone,(epsg,_,_) in ZONES.items()}
    table={k:defaultdict(float) for k in ZONES}
    vector_area={k:0.0 for k in ZONES}
    examined={}
    fingerprints={}
    for level,sign in LEVEL_SIGNS.items():
        path=source/f"GSHHS_{resolution}_L{level}.shp"
        if not path.is_file():
            raise FileNotFoundError("Missing required GSHHG polygon hierarchy: "+str(path))
        fingerprints[f"L{level}"]=_fingerprint(path)
        count=0;split_count=0
        for geometry in _iter_shapefile(path):
            if subset_poly is not None:
                if not geometry.intersects(subset_poly):continue
                geometry=geometry.intersection(subset_poly)
            if not geometry.is_valid:geometry=make_valid(geometry)
            for piece in _split_dateline(geometry):
                if not piece.is_valid:piece=make_valid(piece)
                for zone,t in origins.items():
                    if piece.bounds[3] < ZONES[zone][1] or piece.bounds[1] > ZONES[zone][2]:
                        continue
                    for poly in _zone_geometry(piece,zone,t.transform if False else t):
                        vector_area[zone]+=sign*poly.area
                        _accumulate(poly,sign,table[zone],block)
                        split_count+=1
            count+=1
        examined[f"L{level}"]=dict(source_polygons=count,projected_zone_polygons=split_count)
    return table,vector_area,examined,fingerprints


def _records(table):
    inv={z:Transformer.from_crs(epsg,4326,always_xy=True)
         for z,(epsg,_,_) in ZONES.items()}
    out=[]
    diagnostics={}
    for zone,areas in table.items():
        if not areas:continue
        keys=[(x,y,a) for (x,y),a in areas.items() if a>1e-6]
        negatives=sum(a < -1e-5 for a in areas.values())
        over=sum(a>CELL_AREA+1e-3 for a in areas.values())
        if negatives or over:
            raise ValueError(f"GSHHG level topology invalid in zone {zone}: negative={negatives}, over={over}")
        for x,y,area in keys:
            if area>CELL_AREA:area=CELL_AREA  # tiny floating point rounding only
            lon,lat=inv[zone].transform((x+.5)*CELL,(y+.5)*CELL)
            if not -180.00001<=lon<=180.00001 or not -90.00001<=lat<=90.00001:
                # An exceptionally polar grid centre may fall outside the
                # official geographic cap despite a valid partial overlap.
                lon=lat=np.nan
            out.append((f"{x}_{y}" if zone=="G" else f"{zone}_{x}_{y}",
                        zone,f"EPSG:{ZONES[zone][0]}",int(x),int(y),
                        float(area/1e6),float(area/CELL_AREA),lon,lat))
        diagnostics[zone]=dict(positive_land_cells=len(keys),
                               negative_candidates=negatives,
                               overfilled_cells=over)
    frame=pd.DataFrame(out,columns=[
        "grid_id","zone","grid_crs","grid_x","grid_y",
        "land_area_km2","land_fraction","longitude","latitude"])
    if frame.grid_id.duplicated().any():
        raise ValueError("Global vs polar GF10 ID collision")
    return frame,diagnostics


def build(root,source,resolution="f",legacy=None,tag="gf10_global_land_gshhg_f_v1",
          bounds=None,block=24,require_legacy=False):
    if not re.fullmatch(r"gf10_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use versioned gf10_* tag")
    if bounds is not None and require_legacy:
        raise ValueError("Cannot compare all urban legacy grid cells against a regional pilot")
    table,areas,counts,hashes=compute(source,resolution,subset=bounds,block=block)
    frame,stats=_records(table)
    if frame.empty:raise ValueError("No land polygons found in requested range")
    sum_out={z:float(frame.loc[frame.zone.eq(z),"land_area_km2"].sum()*1e6) for z in ZONES}
    comparison={}
    for zone,v in areas.items():
        if v<=0:
            if sum_out[zone]>0:raise ValueError("Land/ocean polygon topology invalid")
            comparison[zone]=0.0
            continue
        relative=abs(sum_out[zone]-v)/v
        comparison[zone]=float(relative)
        if relative>.003:
            raise ValueError(f"Land area mass conservation failed {zone}: {relative:.6f}")
    old=[]
    if legacy:
        frame0=pd.read_parquet(legacy,columns=["grid_id","grid_x","grid_y"])
        if frame0.grid_id.duplicated().any():raise ValueError("Legacy GF10 duplicate IDs")
        gf=frame.loc[frame.zone.eq("G"),"grid_id"]
        old=sorted(set(frame0.grid_id.astype(str))-set(gf.astype(str)))
        if require_legacy and old:
            raise ValueError(f"{len(old)} legacy urban cells not on land according to selected GSHHG: "
                             +str(old[:12]))
    # Only one immutable output root. Full global table may be >1.5M cells;
    # write a shard for every zone, plus a global table for joining.
    dest=safe_output(root,"data/reference/"+tag)
    if dest.exists():raise FileExistsError("Refusing to overwrite frozen global grid: "+str(dest))
    dest.mkdir(parents=True,exist_ok=False)
    frame.sort_values(["zone","grid_x","grid_y"]).to_parquet(
        dest/"gf10_global_all_land.parquet",index=False,compression="zstd")
    for zone in ZONES:
        part=frame.loc[frame.zone.eq(zone)].copy()
        if not part.empty:
            part.to_parquet(dest/f"gf10_zone_{zone}.parquet",index=False,compression="zstd")
    if legacy:
        pd.DataFrame({"legacy_grid_id_unmatched":old}).to_csv(
            dest/"legacy_urban_cells_not_in_new_land.csv",index=False)
    qa=dict(status=("PILOT_REGIONAL_ONLY" if bounds is not None else
                    "GLOBAL_GSHHG_SOURCE_COVERAGE_QA_PASSED"),
            source="GSHHG v2.3.7 original full-resolution polygon hierarchy",
            resolution=resolution,geography="land polygons from L1-L2+L3-L4+L6 grounding line",
            source_subsetting_bounds=bounds,
            no_land_area_threshold=True,
            small_islands_included_if_represented_in_GSHHG=True,
            warning="No shoreline database guarantees literally every tiny islet; GSHHG full-res source is authoritative within its version",
            n_GF10_land_cells=int(len(frame)),
            n_by_zone={z:int(sum(frame.zone.eq(z))) for z in ZONES},
            n_coastal_or_partial=int(frame.land_fraction.lt(1-1e-8).sum()),
            total_land_area_km2=float(frame.land_area_km2.sum()),
            per_zone_polygon_to_grid_relative_area_error=comparison,
            shoreline_feature_count=counts,
            coastline_shp_sha256=hashes,
            all_grid_cell_area_km2=100,
            global_crs="EPSG:6933",polar_north_crs="EPSG:6931",polar_south_crs="EPSG:6932",
            global_zone_latitude_limit=86,
            existing_6933_grid_ids_unchanged=True,
            legacy_urban_missing_count=len(old),
            legacy_urban_missing_example=old[:40],
            no_GEE_jobs=True,no_downloads=True,
            publication_ready_without_independent_validation=False,
            immutable_read_only_historical_GF10=True,
            caution="Downstream fig2 GEE/static tools assume EPSG6933; polar adapter required.")
    atomic_json(dest/"gf10_global_land_qc.json",qa)
    return qa


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--source",type=Path,required=True,
                   help="Extracted GSHHS_shp/f directory with L1,L2,L3,L4,L6")
    p.add_argument("--resolution",choices=["f","h","i","l","c"],default="f")
    p.add_argument("--legacy",type=Path,
                   help="Earlier 2020 urban grid for unchanged-ID coverage audit")
    p.add_argument("--require-legacy",action="store_true")
    p.add_argument("--tag",default="gf10_global_land_gshhg_f_v1")
    p.add_argument("--smoke-bounds",type=float,nargs=4,metavar=("W","S","E","N"))
    p.add_argument("--block",type=int,default=24)
    a=p.parse_args(argv)
    print(json.dumps(build(a.root,a.source,a.resolution,a.legacy,a.tag,
                           a.smoke_bounds,a.block,a.require_legacy),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
