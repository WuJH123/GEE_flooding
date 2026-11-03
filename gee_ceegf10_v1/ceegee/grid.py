"""Frozen GF10 origin=0m EPSG:6933; local parquet is sole authority."""
from pathlib import Path
import json

EXPECTED_CELLS = 1_395_471
EXPECTED_KM2 = 133_095_959.350
CELL_M = 10_000


def load_grid(path):
    import pandas as pd
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f'Copy frozen GF10 Parquet to {source}; no alternative urban grid permitted')
    cols = ['grid_id','grid_x','grid_y','land_area_km2']
    g = pd.read_parquet(source, columns=cols)
    if len(g) != EXPECTED_CELLS or g.grid_id.isna().any() or g.grid_id.duplicated().any():
        raise ValueError(f'Unexpected frozen GF10 count or IDs: {len(g)}')
    if abs(float(g.land_area_km2.sum()) - EXPECTED_KM2) > 0.01:
        raise ValueError('Land area checksum failed')
    if not all(pd.api.types.is_integer_dtype(g[x]) for x in ('grid_x','grid_y')):
        raise ValueError('GF10 grid_x/grid_y must be integers, not reprojected coordinates')
    if not g.land_area_km2.between(0,100.000001,inclusive='right').all():
        raise ValueError('Land area outside (0,100] km2')
    return g


def limits(grid):
    return dict(minx=int(grid.grid_x.min()),maxx=int(grid.grid_x.max()+1),
                miny=int(grid.grid_y.min()),maxy=int(grid.grid_y.max()+1),
                count=len(grid),land_km2=float(grid.land_area_km2.sum()))


def bounds_m(x, y):
    return [int(x)*CELL_M,int(y)*CELL_M,(int(x)+1)*CELL_M,(int(y)+1)*CELL_M]


def select_pilot(grid, number=16):
    """Deterministic full-land, partially-land, small-island + global-spread sample."""
    import numpy as np
    from pyproj import Transformer
    targets=[(114.3,30.6), (90.4,23.8),(-0.12,51.5),(3.38,6.52),(-74,40.7),
             (-99.1,19.4),(-46.6,-23.55),(151.2,-33.86),(139.7,35.7),
             (28.0,-26.2),(72.8,19.0),(13.4,52.5),(-70.7,-33.45),(-157.8,21.3)]
    coords = np.stack([grid.grid_x.to_numpy(),grid.grid_y.to_numpy()],axis=1)
    idxs=[]
    tr=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    for lon,lat in targets:
        px,py=tr.transform(lon,lat)
        q=np.array([px/CELL_M-.5,py/CELL_M-.5])
        # Fast vectorized approximate center-distance in GF10-index space.
        dist=np.sum((coords-q)**2,axis=1)
        idx=int(dist.argmin())
        if idx not in idxs: idxs.append(idx)
    for mode in ('tiny','coast'):
        sub=grid[grid.land_area_km2.lt(1) if mode=='tiny' else grid.land_area_km2.between(20,80)]
        for idx in sub.sample(n=min(2,len(sub)),random_state=20261103).index:
            if int(idx) not in idxs: idxs.append(int(idx))
    if number < 8: raise ValueError('At least 8 pilot cells required for distinct climates and coast checks')
    records=grid.iloc[idxs[:max(number,8)]].copy()
    records['pilot_type'] = ['geographical_anchor']*min(len(targets),len(records)) + ['partial_or_tiny_land']*max(0,len(records)-len(targets))
    return records[['grid_id','grid_x','grid_y','land_area_km2','pilot_type']].reset_index(drop=True)


def strata(grid, count=12):
    """Equal-height EPSG6933 horizontal bands; not a random sampling of cells."""
    lim=limits(grid)
    height=lim['maxy']-lim['miny']
    return [(i,max(lim['miny'],lim['miny']+height*i//count),
                min(lim['maxy'],lim['miny']+height*(i+1)//count)) for i in range(count)]


def pilot_features(ee, sample):
    feat=[]
    for row in sample.itertuples(index=False):
        polygon=ee.Geometry.Rectangle(bounds_m(row.grid_x,row.grid_y), ee.Projection('EPSG:6933'), False)
        feat.append(ee.Feature(polygon,{'grid_id':str(row.grid_id), 'land_area_km2':float(row.land_area_km2),
            'pilot_type':str(row.pilot_type)}))
    return ee.FeatureCollection(feat)
