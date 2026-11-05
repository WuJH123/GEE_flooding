"""Deterministic GF10 tile cropping and EPSG:6933 seam risk detection.

All projected native 10 km cells have integer global EPSG6933 indices; no
antimeridian-spanning polygons may be submitted for automatic raster export.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from functools import lru_cache
from pathlib import Path
import math

CELL=10000
# The official world cylindrical equal-area projected endpoints at lon +/-180.
# We deliberately do not assert EPSG projected rectangles crossing these
# lines have meaningful geographic area; such cells remain quarantined.

@lru_cache(maxsize=1)
def valid_limits():
    from pyproj import Transformer
    p=Transformer.from_crs(4326,6933,always_xy=True)
    west,_=p.transform(-180,0)
    east,_=p.transform(180,0)
    _,south=p.transform(0,-86)
    _,north=p.transform(0,86)
    return west,east,south,north

@dataclass(frozen=True)
class Crop:
    original_key:str
    x0:int
    y0:int
    original_n:int
    x_min:int
    y_min:int
    width:int
    height:int
    n_land:int
    status:str
    reason:str
    def work_bounds(self):
        return [self.x_min*CELL,self.y_min*CELL,
                (self.x_min+self.width)*CELL,(self.y_min+self.height)*CELL]
    def export_bounds(self):
        # Export region surrounds all output pixel centers, NOT tile edges.
        # Epsilon=1m; input is globally aligned to exact 10km/zero origin.
        x0,y0,x1,y1=self.work_bounds()
        return [x0+CELL/2-1,y0+CELL/2-1,x1-CELL/2+1,y1-CELL/2+1]
    def expected_transform(self):
        return [CELL,0,self.x_min*CELL,0,-CELL,(self.y_min+self.height)*CELL]
    def as_record(self):
        return asdict(self)


def crop_tile(frame,x:int,y:int,n:int,margin_m:float=1):
    """Returns cropped, contiguous projected output rectangle for land cells.

    Tested before constructing *any* EE object. Reject seam/out-of-domain
    instead of allowing GDAL/EE to create near-global lon/lat envelopes.
    """
    if n!=10:raise ValueError('MERIT v3 source model validated only for nominal 10x10 parent tiles')
    if margin_m<0 or margin_m>100:raise ValueError('Invalid margin')
    key=f'merit_{x}_{y}_{n}'
    subset=frame.loc[frame.grid_x.between(x,x+n-1)&frame.grid_y.between(y,y+n-1)]
    if subset.empty:return Crop(key,x,y,n,x,y,0,0,0,'SKIP_EMPTY','No GF10 positive land')
    xi=int(subset.grid_x.min());yi=int(subset.grid_y.min())
    width=int(subset.grid_x.max())-xi+1
    height=int(subset.grid_y.max())-yi+1
    base=Crop(key,x,y,n,xi,yi,width,height,len(subset),'SAFE_COMPACT','')
    l,b,r,t=base.work_bounds()
    vl,vr,vb,vt=valid_limits()
    if l<vl+margin_m or r>vr-margin_m or b<vb+margin_m or t>vt-margin_m:
        return Crop(key,x,y,n,xi,yi,width,height,len(subset),'QUARANTINE_SEAM',
                    'Cropped rectangle intersects EPSG:6933 valid-world edge; no automatic EE export')
    if width*height>100:raise ValueError('Compact crop larger than parent tile')
    return base


def projected_region_width_excess(width,height,max_pixels=200):
    return int(width)*int(height)>int(max_pixels)


def validate_raster_metadata(profile,crop:Crop):
    """Read-only metadata gate; applies to any actual downloaded EE raster."""
    crs=profile['crs']
    if crs not in ('EPSG:6933',6933):raise ValueError('Wrong EPSG:6933 CRS')
    if (profile['width'],profile['height'])!=(crop.width,crop.height):
        raise ValueError(f'Invalid GEE exported shape {(profile["width"],profile["height"])} != {(crop.width,crop.height)}')
    if profile['count']!=16:raise ValueError('MERIT scientific 16-band schema changed')
    t=profile['transform']
    exp=crop.expected_transform()
    if len(t)!=6 or any(abs(a-b)>1e-6 for a,b in zip(t,exp)):
        raise ValueError('Output affine transform is NOT globally aligned to original GF10')
    if projected_region_width_excess(profile['width'],profile['height']):
        raise ValueError('Absurd size for 10x10 GF10 parent task')
    return True
