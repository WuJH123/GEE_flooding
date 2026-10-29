"""Freeze native GF10 2020 urban cells from TWO existing SMOD GeoTIFF stripes.

All generated grid data go to E:\GEE_flooding; input TIFFs are never changed.
"""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer,Geod
from .paths import safe_output,atomic_json

CELL=10000
XMIN=-17360000
YMAX=7320000
HEIGHT=1464

def _sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def _area_ratio(x,y):
    q=np.linspace(0,1,17)
    x0,y0=x*CELL,y*CELL
    xs=np.r_[x0+q*CELL,np.full_like(q,x0+CELL),x0+(1-q)*CELL,np.full_like(q,x0)]
    ys=np.r_[np.full_like(q,y0),y0+q*CELL,np.full_like(q,y0+CELL),y0+(1-q)*CELL]
    lon,lat=Transformer.from_crs(6933,4326,always_xy=True).transform(xs,ys)
    area,_=Geod(ellps='WGS84').polygon_area_perimeter(lon,lat)
    return abs(area)/(CELL*CELL)

def freeze(root,west,east,urban_min=.001,valid_min=.95):
    if not (0<urban_min<=1 and 0<valid_min<=1):raise ValueError('Invalid fractions')
    dest=safe_output(root,'data/reference/grid10_urban_2020.parquet')
    qcfile=safe_output(root,'data/reference/grid10_qc.json')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() or qcfile.exists():raise FileExistsError('Local grid already frozen')
    frames=[];checks=[]
    converter=Transformer.from_crs(6933,4326,always_xy=True)
    for path,xmin in ((Path(west),XMIN),(Path(east),0)):
        with rasterio.open(path) as ds:
            if ds.crs is None or ds.crs.to_epsg()!=6933 or ds.count!=2:
                raise ValueError('Expected EPSG:6933, two bands: '+str(path))
            if (ds.width,ds.height)!=(1736,HEIGHT):raise ValueError('Unexpected stripe shape')
            got=(ds.transform.a,ds.transform.b,ds.transform.c,
                 ds.transform.d,ds.transform.e,ds.transform.f)
            want=(CELL,0,xmin,0,-CELL,YMAX)
            if max(abs(a-b) for a,b in zip(got,want))>1e-4:
                raise ValueError('Invalid global affine alignment: '+str(path))
            urban=ds.read(1,masked=True).filled(np.nan).astype(float)
            valid=ds.read(2,masked=True).filled(np.nan).astype(float)
            for arr in (urban,valid):
                if np.any(np.isfinite(arr)&((arr<-1e-5)|(arr>1.00001))):
                    raise ValueError('Invalid physical band values')
            row,col=np.nonzero(np.isfinite(urban)&np.isfinite(valid)&
                               (urban>=urban_min)&(valid>=valid_min))
            if not len(row):raise ValueError('No eligible cells in '+str(path))
            gx=(xmin//CELL+col).astype('int32')
            gy=(YMAX//CELL-row-1).astype('int32')
            if (urban[row,col]/valid[row,col]>1.01).any():
                raise ValueError('Urban fraction exceeds source-valid fraction')
            lon,lat=converter.transform((gx+.5)*CELL,(gy+.5)*CELL)
            frames.append(pd.DataFrame({
                'grid_id':[f'{x}_{y}' for x,y in zip(gx,gy)],
                'grid_x':gx,'grid_y':gy,'longitude':lon,'latitude':lat,
                'cell_area_m2':np.full(len(gx),100000000,dtype='int64'),
                'urban_fraction_2020':urban[row,col],
                'source_valid_fraction':valid[row,col]}))
            checks.append({'input':str(path),'sha256':_sha(path),'cells':len(row)})
    cells=pd.concat(frames,ignore_index=True).sort_values(['grid_x','grid_y'])
    if cells.grid_id.duplicated().any():raise ValueError('Duplicated 10km cell IDs')
    rng=np.random.default_rng(42)
    ids=rng.choice(len(cells),min(150,len(cells)),replace=False)
    ratios=[_area_ratio(int(cells.iloc[i].grid_x),int(cells.iloc[i].grid_y)) for i in ids]
    if any(abs(r-1)>.005 for r in ratios):raise ValueError('Geodetic cell area mismatch')
    tmp=dest.with_suffix('.parquet.partial')
    cells.to_parquet(tmp,index=False);tmp.replace(dest)
    qc={'status':'PASS_10KM_GRID_CONTRACT','grid_count':len(cells),
        'crs':'EPSG:6933','cell_area_km2':100,'urban_min':urban_min,
        'valid_min':valid_min,'geodesic_area_ratio_min':min(ratios),
        'geodesic_area_ratio_max':max(ratios),'sources':checks,
        'warning':'2020 urban reference domain; missing news is not absence of flooding'}
    atomic_json(qcfile,qc)
    return qc
