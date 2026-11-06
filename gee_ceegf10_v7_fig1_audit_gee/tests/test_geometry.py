import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree
from pyproj import Transformer
from shapely import transform
from cee_v7.geometry import city_match,compute_overlap,loc_assess

def inv(g):
 tr=Transformer.from_crs('EPSG:6933','EPSG:4326',always_xy=True)
 return transform(g,lambda coords:np.column_stack(tr.transform(coords[:,0],coords[:,1])))

def mkcities():
 g1=box(1000,1000,9000,9000);g2=box(11000,11000,15000,15000)
 return {'geoms':[g1,g2],'ids':['U1','U2'],'tree':STRtree([g1,g2])}

def test_unique_ucdb_and_frozen_gf10_geometry():
 shape=inv(box(3000,3000,6000,6000))
 z,err=loc_assess(shape,0,0,mkcities())
 assert err is None
 assert z['city_id']=='U1'
 assert z['grid_geom_fraction']>0.99
 assert z['ucdb_geom_fraction']>0.99

def test_cross_grid_spatial_vagueness_rejected():
 shape=inv(box(9000,9000,11000,11000))
 _,err=loc_assess(shape,0,0,mkcities())
 assert err.startswith('MULTI_GRID')

def test_ucdb_city_unresolved_not_fabricated():
 shape=inv(box(3000,3000,6000,6000))
 _,err=loc_assess(shape,1,1,mkcities())
 assert err.startswith('MULTI_GRID')
 shape=inv(box(15000,15000,16500,16500))
 _,err=loc_assess(shape,1,1,mkcities())
 assert err in {'NO_UCDB_INTERSECTION','NO_AREA_OVERLAP'}

def test_geometry_is_not_flood_footprint():
 shape=inv(box(1000,1000,9000,9000))
 z,err=loc_assess(shape,0,0,mkcities(),max_area_km2=25)
 assert z is None and 'COARSE_LOCATION' in err
