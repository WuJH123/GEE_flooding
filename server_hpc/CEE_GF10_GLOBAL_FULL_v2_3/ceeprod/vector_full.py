"""Full-coverage (715 GF10 tiles) vector polygon/line overlays.

All spatial operations are run on *actual native provider geometries*. GRIP4
and RiverATLAS lines are clipped in EPSG:6933 but lengths measured on WGS84
ellipsoid, NOT falsely called metric lengths in an equal-area projection.

CAVEATS: coastline water portion and native source coverage are separate QA;
geometry of antimeridian-crossing global lines must not be made world-spanning.
"""
from __future__ import annotations
from dataclasses import asdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import os, warnings
import numpy as np
import pandas as pd
from .shared import prepare_directory,read_json,write_json,file_identity
from .discover import discover_family

GEOMS={'admin0':'polygon','admin1':'polygon','ucdb':'polygon','basin':'polygon',
       'roads':'line','river':'line'}

# Each source has a documented native primary ID, discovered using metadata.
# No made-up city/basin codes or random ordering of overlap results.

def _cells(tile):
    import geopandas as gpd
    from shapely import box
    a=pd.read_parquet(tile)
    if len(a)==0:return a,None
    xmin=a.grid_x.to_numpy(dtype='int64')*10000
    ymin=a.grid_y.to_numpy(dtype='int64')*10000
    polys=box(xmin,ymin,xmin+10000,ymin+10000)
    return a,gpd.GeoDataFrame(a[['grid_id','land_area_km2']],geometry=polys,crs='EPSG:6933')

def _bbox_for_tile(cells,source_crs):
    """Conservative native spatial bboxes, splitting the *shortest* dateline arc.

    Crucial for GRIP4: a 600km tile near 180 E/W must NEVER query half the
    world's 25 million lines because a naive bbox spans -179..+179.
    """
    from pyproj import Transformer,CRS
    xmin,ymin,xmax,ymax=map(float,cells.total_bounds)
    crs=CRS.from_user_input(source_crs)
    tr=Transformer.from_crs('EPSG:6933',crs,always_xy=True)
    if not crs.is_geographic:
        vals=tr.transform_bounds(xmin,ymin,xmax,ymax,densify_pts=64)
        if not all(np.isfinite(vals)):raise ValueError('GF10 tile bounds cannot project to source CRS')
        return [tuple(vals)]
    # Project each side densely so curved 6933->geographic edges are included.
    n=65
    along=np.linspace(0.,1.,n)
    xs=np.concatenate((xmin+(xmax-xmin)*along,np.full(n,xmax),
                       xmin+(xmax-xmin)*along,np.full(n,xmin)))
    ys=np.concatenate((np.full(n,ymin),ymin+(ymax-ymin)*along,
                       np.full(n,ymax),ymin+(ymax-ymin)*along))
    lon,lat=tr.transform(xs,ys)
    lon=np.asarray(lon,dtype=float);lat=np.asarray(lat,dtype=float)
    valid=np.isfinite(lon)&np.isfinite(lat)&(np.abs(lat)<=90)
    if valid.sum()<len(lon)*.95:
        raise ValueError('Many projected geographic bounds invalid; polar source requires dedicated audit')
    a=np.sort(np.mod(lon[valid],360.))
    gaps=np.diff(np.r_[a,a[0]+360.])
    idx=int(np.argmax(gaps))
    start=float(a[(idx+1)%len(a)])
    arc=float(360.-gaps[idx])
    if arc>45:
        raise ValueError(f'Unexpected GF10 tile >45 degree longitude arc; possible antimeridian/polar failure: {arc}')
    end=start+arc
    south=float(np.min(lat[valid])-.05);north=float(np.max(lat[valid])+.05)
    ranges=[]
    cur=start
    # Split at both 180 and 360; normalize each into -180..180.
    while cur<end+1e-8:
        if cur>=end-1e-8:break
        nextedge=min(end,180.*(int(np.floor(cur/180))+1))
        if nextedge<=cur+1e-9:nextedge=end
        left=cur if cur<180 else cur-360
        right=nextedge if nextedge<=180 else nextedge-360
        if nextedge==360.:right=0.
        if right<left:
            # Special case cur>=180: subtract 360 from both endpoints.
            right=nextedge-360.
        ranges.append((max(-180.,left-.05),max(-90.,south),
                       min(180.,right+.05),min(90.,north)))
        cur=nextedge
    if not ranges:raise ValueError('Empty geographic spatial query longitude range')
    if any(z[2]<z[0] or z[2]-z[0]>46 for z in ranges):
        raise ValueError('Spatial query rectangle is not a small local bbox: '+str(ranges))
    return ranges

def _read_bbox(source,layer,crs,bboxes,columns=None):
    import pyogrio, geopandas as gpd
    frames=[]
    for bbox in bboxes:
        try:
            frame=pyogrio.read_dataframe(source,layer=layer,bbox=bbox,columns=columns,use_arrow=True,
                                           on_invalid='warn')
        except (TypeError,ValueError,ImportError,RuntimeError) as e:
            # Arrow GDAL read may not work for older FileGDB drivers.
            frame=pyogrio.read_dataframe(source,layer=layer,bbox=bbox,columns=columns,on_invalid='warn')
        if not frame.empty:frames.append(frame)
    if not frames:return gpd.GeoDataFrame(geometry=[],crs=crs)
    sourceframes=pd.concat(frames,ignore_index=True)
    # A near-antimeridian source can be returned by both half queries.
    if len(frames)>1:
        sourceframes=sourceframes.loc[~sourceframes.geometry.to_wkb().duplicated()].copy()
    if not sourceframes.crs:raise ValueError('Loaded original vector lost native CRS')
    return sourceframes

def _overlay_source(task):
    import geopandas as gpd
    import shapely
    from pyproj import Transformer,Geod
    from shapely import transform as transform_geom
    item,tile,outdir,jid=task
    tile=Path(tile);root=Path(outdir)
    dest=root/'tiles'/tile.name
    q=dest.with_suffix('.qc.json')
    cross=root/'crosswalk'/tile.name
    if dest.exists() and q.exists():
        meta=read_json(q)
        if meta.get('job_id')==jid and meta.get('status')=='OK':
            import pyarrow.parquet as pq
            if pq.ParquetFile(dest).metadata.num_rows==meta['n_grid'] and (item['family'] in ('roads','river') or cross.exists()):
                return {'status':'REUSED','n_grid':meta['n_grid'],'n_matched':meta['n_matched']}
        raise ValueError('Existing vector output invalid/incomplete: '+str(dest))
    if dest.exists() or q.exists() or cross.exists():
        raise FileExistsError('Partial/unpaired source files; quarantine to new versioned path: '+str(dest))
    grid,cells=_cells(tile)
    import pyogrio
    query=_bbox_for_tile(cells,item['native_crs'])
    src=_read_bbox(item['path'],item['layer'],item['native_crs'],query,
        columns=[item['id_field']] if item.get('id_field') else [])
    if not src.empty:
        src=src.loc[src.geometry.notna()&~src.geometry.is_empty].copy()
        if src.empty:raise ValueError('Source returned only empty geometries in indexed spatial region')
        # Never coerce original provider IDs into floating-point values.
        if item.get('id_field') and item['id_field'] not in src.columns:
            raise ValueError('Provider stable ID field absent: '+item['id_field'])
        if item.get('id_field') and src[item['id_field']].isna().any():
            raise ValueError('Original provider identity has null values, cannot fabricate IDs')
        # Transform source geometries, not the 1.4M frozen grid.
        src=src.to_crs('EPSG:6933')
        src=src.loc[src.geometry.notna()&~src.geometry.is_empty].reset_index(drop=True)
    n=len(grid)
    line_mode=GEOMS[item['family']]=='line'
    n_matches=np.zeros(n,dtype=np.int32)
    measure=np.zeros(n,dtype=np.float64)
    primary=np.full(n,None,dtype=object)
    second=np.zeros(n,dtype=np.float64)
    longrows=[]
    ambiguous=np.zeros(n,dtype=bool)
    native_drops=0
    if len(src):
        if len(src)>400_000:
            raise MemoryError(f'Native GDB returned {len(src)} source objects in one 64x64 GF10 tile: spatial index/bbox read inefficient; refuse RAM blowup')
        from shapely import STRtree
        geoms=np.asarray(cells.geometry.values)
        segments=np.asarray(src.geometry.values)
        # Exclude geometries with impossibly large widths caused by missed
        # date-line splitting. Do NOT emit a fabricated zero for these cells.
        bounds=shapely.bounds(segments)
        suspicious=(bounds[:,2]-bounds[:,0])>15_000_000
        if np.any(suspicious):
            raise ValueError('Provider has world-spanning geometry after reprojection; GIS date-line repair required for '+item['family'])
        tree=STRtree(geoms)
        pair=tree.query(segments,predicate='intersects')
        if pair.size:
            feat_i,grid_i=pair
            # Up to hundreds of thousands of spatial candidates, process in
            # bounded C++ shapely vectorized batches to constrain peak RAM.
            geod=Geod(ellps='WGS84')
            to_ll=Transformer.from_crs(6933,4326,always_xy=True)
            identifiers=src[item['id_field']].astype(str).to_numpy() if item.get('id_field') else None
            for start in range(0,len(feat_i),30000):
                subf=feat_i[start:start+30000]
                subg=grid_i[start:start+30000]
                clipped=shapely.intersection(segments[subf],geoms[subg])
                if line_mode:
                    for loc,geom in zip(subg,clipped):
                        if geom is None or geom.is_empty:continue
                        if geom.geom_type not in ('LineString','MultiLineString','GeometryCollection'):
                            continue
                        ll=transform_geom(geom,to_ll.transform,interleaved=False)
                        # A boundary-only intersection can produce a point
                        # in a GeometryCollection; only genuine line parts
                        # contribute length, never a point or polygon.
                        parts=(list(ll.geoms) if ll.geom_type=='GeometryCollection' else [ll])
                        km=sum(abs(geod.geometry_length(part))/1000 for part in parts
                           if part.geom_type in ('LineString','MultiLineString'))
                        if not np.isfinite(km) or km<0:raise ValueError('Nonfinite geodesic road/river length')
                        if km<=0:continue
                        measure[loc]+=km;n_matches[loc]+=1
                else:
                    for feat,loc,geom in zip(subf,subg,clipped):
                        if geom is None or geom.is_empty:continue
                        area=shapely.area(geom)/1e6
                        if not np.isfinite(area) or area<0:raise ValueError('Invalid projected equal-area polygon intersection')
                        if area<=1e-7:continue
                        n_matches[loc]+=1
                        # Guarantee no stochastic choice when multiple city/
                        # country/basin polygons overlap a grid cell.
                        if area>measure[loc]:
                            second[loc]=measure[loc]
                            measure[loc]=area
                            primary[loc]=identifiers[feat]
                        elif area>second[loc]:second[loc]=area
                        longrows.append((str(grid.grid_id.iloc[loc]),identifiers[feat],float(area)))
    frame=pd.DataFrame({'grid_id':grid.grid_id.to_numpy(),
           f'{item["family"]}_n_feature_intersections':n_matches,
           f'{item["family"]}_spatial_query_done':np.ones(n,dtype=bool)})
    if line_mode:
        frame[f'{item["family"]}_length_km_geodesic']=measure
        frame[f'{item["family"]}_zero_length_source_coverage_unverified']=(n_matches==0)
        frame[f'{item["family"]}_length_density_km_per_land_km2']=np.divide(measure,
                   grid.land_area_km2.to_numpy(float),out=np.full(n,np.nan),where=grid.land_area_km2.to_numpy(float)>0)
    else:
        frame[f'{item["family"]}_dominant_native_id']=primary
        frame[f'{item["family"]}_dominant_intersection_km2']=measure
        frame[f'{item["family"]}_second_largest_intersection_km2']=second
        frame[f'{item["family"]}_n_overlap']=n_matches
        frame[f'{item["family"]}_uncertain_multiple']=n_matches>1
        frame[f'{item["family"]}_fraction_full_cell']=measure/100.
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+'.writing')
    frame.to_parquet(tmp,index=False,compression='zstd');os.replace(tmp,dest)
    if not line_mode:
        cross.parent.mkdir(parents=True,exist_ok=True)
        t=cross.with_name(cross.name+'.writing')
        pd.DataFrame(longrows,columns=['grid_id',item['id_field'],'intersect_km2']).to_parquet(t,index=False,compression='zstd')
        os.replace(t,cross)
    write_json(q,{'status':'OK','job_id':jid,'n_grid':n,'n_matched':int((n_matches>0).sum()),
       'source_geometry':'native vector, equal-area polygon intersection / ellipsoid line geodesic length',
       'tile':tile.name,'coastline_land_clipping':'UNVERIFIED','native_source_coverage':'NOT_FULLY_INDEPENDENTLY_VERIFIED',
       'n_provider_features_in_bbox':len(src),'n_candidate_pairs':int(n_matches.sum())})
    return {'status':'WROTE','n_grid':n,'n_matched':int((n_matches>0).sum())}

def run(root,family,workers=12):
    if family not in GEOMS:raise ValueError(family)
    if not 1<=workers<=32:raise ValueError('Workers 1..32 for Windows per-source vector task')
    root=Path(root)
    source=asdict(discover_family(root,family))
    stage=root/'data/working/cee_all_tiles64_v11/tiles'
    tiles=sorted(stage.glob('tile_*.parquet'))
    if len(tiles)!=715:raise ValueError('Refuse to call a partial 5000-grid trial a global product')
    out,jid=prepare_directory(root/'data/derived/cee_all_global_v2/vector'/family,
         {'source':source,'source_file':file_identity(source['path']),'frozen_grid':file_identity(root/'gf10_global_nonantarctic_land.parquet'),
          'algorithm':'gf10_all715_exact_area_or_wgs84_geodesic_v2'})
    tasks=[(source,str(p),str(out),jid) for p in tiles]
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        tasks_future=[ex.submit(_overlay_source,t) for t in tasks]
        for i,f in enumerate(as_completed(tasks_future),1):
            results.append(f.result())
            if i%25==0 or i==len(tasks):print(f'[vector-{family}] {i}/715, new={sum(x["status"]=="WROTE" for x in results)}',flush=True)
    rows=sum(z['n_grid'] for z in results)
    if rows!=1_395_471:raise ValueError('Vector 715 tiles did not conserve 1,395,471 GF10 IDs')
    qc={'status':'ALL_715_GF10_TILES_VECTOR_PROCESSED_SOURCE_COVERAGE_AND_LAND_QA_REQUIRED',
      'family':family,'n_grid':rows,'n_tiles':len(results),'n_matched_tiles_sum':sum(z['n_matched'] for z in results),
      'n_written':sum(z['status']=='WROTE' for z in results), 'n_reused':sum(z['status']=='REUSED' for z in results),
      'source_native_id':source['id_field'],'source_layer':source['layer'],
      'rasterized_or_pilot':False,'all_fields_in_model':False,'publication_ready':False,
      'method':'area_overlap_full_cell' if GEOMS[family]=='polygon' else 'geodesic_clipped_line_length'}
    write_json(out/'run_qc.json',qc)
    return qc
