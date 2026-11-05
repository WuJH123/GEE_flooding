"""Explicit 10km projected lattice safety and frozen GF10 ID auditing.

Boundary-cell Table export is used only where a nominal 10x10 image region
would exceed the EPSG:6933 valid projection range or fail projected roundtrip.
No failed large GeoTIFF is ever cropped into the scientific registry.
"""
from __future__ import annotations
import math, json, pathlib, hashlib, datetime
from dataclasses import dataclass
from pyproj import Transformer

CELL=10000
GRID_COUNT=1395471
X_LIMIT=abs(Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True).transform(180,0)[0])
Y_LIMIT=abs(Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True).transform(0,86)[1])

@dataclass(frozen=True)
class Tile:
    x:int
    y:int
    n:int=10
    @property
    def key(self):return f'merit_{self.x}_{self.y}_{self.n}'
    @property
    def bounds(self):return (self.x*CELL,self.y*CELL,(self.x+self.n)*CELL,(self.y+self.n)*CELL)
    @property
    def transform(self):return (CELL,0,self.x*CELL,0,-CELL,(self.y+self.n)*CELL)
    def point(self,grid_x,grid_y):
        if not (self.x<=grid_x<self.x+self.n and self.y<=grid_y<self.y+self.n):raise ValueError('cell outside 10x10')
        return ((grid_x+.5)*CELL,(grid_y+.5)*CELL)

def projected_mode(tile):
    # 2-pixel safety margin to exclude pathological backprojected half-cell regions.
    l,b,r,t=tile.bounds
    if min(l,-r)<-X_LIMIT+1000 or max(r,-l)>X_LIMIT-1000:
        return 'POINT_TABLE'
    if b < -Y_LIMIT+1000 or t > Y_LIMIT-1000:
        return 'POINT_TABLE'
    return 'FIXED_RASTER'

def pixel_centers_region(tile):
    # EE export region's outward pixel-inclusion rounding at exact cell boundaries
    # previously produced 10x11. Center envelope prevents fractional edge expansion.
    l,b,r,t=tile.bounds
    if projected_mode(tile)!='FIXED_RASTER':raise ValueError('Boundary blocks must not use raster export')
    return (l+CELL/2,b+CELL/2,r-CELL/2,t-CELL/2)

def validate_frozen_subset(g,tile):
    z=g[g.grid_x.between(tile.x,tile.x+tile.n-1)&g.grid_y.between(tile.y,tile.y+tile.n-1)]
    if z.empty:raise ValueError('empty GF10 land subset')
    if len(z)>tile.n**2 or z.grid_id.duplicated().any():raise ValueError('duplicate GF10')
    for r in z.itertuples():
        if r.grid_id!=f'{int(r.grid_x)}_{int(r.grid_y)}':raise ValueError('grid key mismatch')
        cx,cy=tile.point(int(r.grid_x),int(r.grid_y))
        if not(-X_LIMIT<cx<X_LIMIT and -Y_LIMIT<cy<Y_LIMIT):
            raise ValueError(f'Frozen cell center outside EPSG6933 area: {r.grid_id}; must be flagged COVERAGE_LIMIT')
    return z.copy()

def hash_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def atomic_json(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.writing');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf8');tmp.replace(p)

def load(path,default=None):
    p=pathlib.Path(path)
    return json.loads(p.read_text(encoding='utf8')) if p.exists() else default

def expected_ids(grid,tile):
    a=validate_frozen_subset(grid,tile)
    return set(a.grid_id.astype(str))

def template_report(old_ledger):
    rows=load(old_ledger,[])
    return {'entries':[{k:v for k,v in r.items() if k in ('key','state','local_qc_pass','superseded_by','eecu_hours')}
                       for r in rows], 'invalid': [r['key'] for r in rows if r.get('state')=='SUCCEEDED' and not r.get('local_qc_pass') and not r.get('superseded_by')]}
