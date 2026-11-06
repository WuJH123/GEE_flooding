"""Geometry-first, never a flooded-area assumption. GEOS in 6933 equal-area plane."""
from __future__ import annotations
import hashlib,math, pathlib
import numpy as np
from shapely import from_wkb,from_wkt,transform
from shapely.geometry import shape,box
from shapely.strtree import STRtree
from pyproj import Transformer
TR=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)


def parse_shape(value):
    if value is None:return None
    if hasattr(value,'geom_type'):return value
    if isinstance(value,memoryview):value=value.tobytes()
    if isinstance(value,(bytes,bytearray)):
        return from_wkb(bytes(value))
    if isinstance(value,str):return from_wkt(value)
    if isinstance(value,dict):return shape(value)
    raise TypeError('Unknown raw geocoded geometry format '+str(type(value)))

def project(wgs84):
    return transform(wgs84,lambda coords:np.column_stack(TR.transform(coords[:,0],coords[:,1])))

def geometry_identity(geom):return hashlib.sha256(geom.wkb).hexdigest()

def compute_overlap(geom,integer_x,integer_y):
    tile=box(integer_x*10000,integer_y*10000,(integer_x+1)*10000,(integer_y+1)*10000)
    total=geom.area
    return float(geom.intersection(tile).area/total) if total>0 else 0.0


def load_cities(gpkg,city_field=None,layer=None):
    import geopandas as gpd
    import pyogrio
    p=pathlib.Path(gpkg)
    if not p.is_file():raise FileNotFoundError('Official UCDB GeoPackage missing: '+str(p))
    layers=pyogrio.list_layers(str(p))
    all_names=[str(n) for n,t in layers]
    geoms=[str(n) for n,t in layers if 'polygon' in str(t).lower() or 'unknown' in str(t).lower()]
    if layer is None:
        # Figure1 previously used the official GENERAL_CHARACTERISTICS layer.
        known=[n for n in geoms if n=='GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A']
        if known:layer=known[0]
        elif len(geoms)==1:layer=geoms[0]
        else:
            raise ValueError('UCDB has multiple polygon layers; --city-layer required: '+str(geoms))
    if layer not in all_names:raise ValueError('Requested UCDB layer missing: '+str(layer))
    info=pyogrio.read_info(str(p),layer=layer)
    fields=set(info['fields'])
    candidates=[c for c in ['ID_UC_G0','ID_UC','ID_UC_G0_2025','UC_ID','city_id'] if c in fields]
    if not city_field:
        if not candidates:raise ValueError('No verifiable UCDB city key; --city-field must be selected from '+str(sorted(fields)))
        city_field=candidates[0]  # Figure1 uses ID_UC_G0 first, then ID_UC
    if city_field not in fields:raise ValueError('Specified city key not found in official UCDB')
    city=gpd.read_file(str(p),layer=layer,columns=[city_field],engine='pyogrio')
    if city.crs is None:raise ValueError('Official UCDB CRS missing')
    if city[city_field].isna().any() or city[city_field].duplicated().any():raise ValueError('Official UCDB city ID invalid')
    city=city.to_crs('EPSG:6933')
    if city.geometry.isna().any() or city.geometry.is_empty.any() or (~city.is_valid).any():
        raise ValueError('Official UCDB city polygons invalid; audit before intersection')
    geoms=list(city.geometry)
    return {'ids':city[city_field].astype(str).tolist(),'geoms':geoms,'tree':STRtree(geoms),
            'layer':layer,'field':city_field,'crs':str(city.crs),'n_cities':len(city)}

def city_match(projected,ref,threshold=0.85,margin=0.15):
    if projected.area<=0:return None,0.0,0.0,'ZERO_AREA'
    idx=ref['tree'].query(projected)
    if len(idx)==0:return None,0.0,0.0,'NO_UCDB_INTERSECTION'
    measures=[]
    for i in idx:
        i=int(i)
        frac=float(projected.intersection(ref['geoms'][i]).area/projected.area)
        if frac>0:measures.append((frac,ref['ids'][i]))
    if not measures:return None,0.0,0.0,'NO_AREA_OVERLAP'
    measures.sort(reverse=True)
    a,city=measures[0];b=measures[1][0] if len(measures)>1 else 0.0
    if a<threshold or a-b<margin:return None,a,b,'AMBIGUOUS_OR_LOW_CITY_OVERLAP'
    return city,a,b,'UCDB_GEOMETRIC_ATTRIBUTION'


def loc_assess(source_geom,grid_x,grid_y,cities,max_area_km2=25.,min_grid_fraction=0.85,
               min_city_fraction=0.85):
    try:
        g=parse_shape(source_geom)
        if g is None or g.is_empty or not g.is_valid:return None,'INVALID_WGS84_GEOMETRY'
        if g.geom_type not in ('Polygon','MultiPolygon'):return None,'NON_POLYGON_SOURCE_GEOCODE'
        if g.bounds[2]-g.bounds[0]>=180:return None,'ANTIMERIDIAN_GEOCODE_NEEDS_REVIEW'
        if not(-90<=g.bounds[1]<=90 and -90<=g.bounds[3]<=90):return None,'INVALID_LATITUDE'
        p=project(g)
        if p.is_empty or not p.is_valid or p.area<=0:return None,'INVALID_PROJECTED_GEOMETRY'
        area=p.area/1e6
        if area>max_area_km2:return None,'COARSE_LOCATION_GEOMETRY_GT_'+str(max_area_km2)+'KM2'
        f=compute_overlap(p,int(grid_x),int(grid_y))
        if f<min_grid_fraction:return None,'MULTI_GRID_OR_WRONG_GF10_'+str(round(f,4))
        city,c1,c2,method=city_match(p,cities,threshold=min_city_fraction)
        if city is None:return None,method
        return {'city_id':city,'ucdb_geom_fraction':c1,'ucdb_runnerup_fraction':c2,
                'grid_geom_fraction':f,'geocoded_area_km2':area,'geometry_type':g.geom_type,
                'source_geom_sha256':geometry_identity(g),'city_method':method},None
    except Exception as exc:
        return None,'GEOMETRY_ERROR_'+type(exc).__name__
