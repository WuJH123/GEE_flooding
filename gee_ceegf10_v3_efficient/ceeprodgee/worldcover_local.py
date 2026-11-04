"""Local-first ESA WorldCover 2021 10 m -> fixed GF10 10 km categorical stats.

One nearest-neighbour source-category reprojection per original COG, not one
reprojection per class. All 11 land-cover classes, GSHHG land and valid coverage
are aggregated at the FINAL 10 m EPSG6933 pixel lattice for bounded 5x5 tiles.
No 100m majority/mode resampling; class labels are never averaged. The method
is a 10m equal-area rasterization APPROXIMATION, and must pass independent
Gate-C coastline/WorldCover tests to qualify as a research data product.
"""
from __future__ import annotations
import argparse,json,os,pathlib,hashlib,concurrent.futures,traceback
from . import coast,grid,contract,qc
import numpy as np

PPC=1000 # 10 km / 10 m
WC_CODES=contract.WC_CODES

def aggregate_categories(source,land,px_per_cell=1000):
    """Make 25 bands in exact EE Gate-C order from two 10 m boolean arrays.

    Pixel centres in EPSG6933; native 10m equal-area rasterization approximates
    edge intersections. Product-specific QA must compare against independent
    10m fractional exact coverage and frozen GSHHG vector land fraction.
    """
    if source.shape!=land.shape or source.ndim!=2 or source.shape[0]!=source.shape[1]:
        raise ValueError('Source/land must be square and equal-sized')
    n=source.shape[0]//px_per_cell
    if n*px_per_cell!=source.shape[0]:raise ValueError('Image dimensions not aligned to GF10')
    land=np.asarray(land,dtype=bool)
    good=np.isin(source,WC_CODES)
    def frac(binary):
        return binary.reshape(n,px_per_cell,n,px_per_cell).sum(axis=(1,3),dtype=np.int64)/(px_per_cell**2)
    lf=frac(land)
    valid=frac(good)
    land_valid=frac(good & land)
    full=[];inside=[]
    for c in WC_CODES:
        a=source==c
        full.append(np.where(valid>0,frac(a),np.nan))
        joint=frac(a&land)
        inside.append(np.divide(joint,lf,out=np.full_like(joint,np.nan),where=land_valid>0))
    land_valid_ratio=np.divide(land_valid,lf,out=np.full_like(lf,np.nan),where=lf>0)
    return np.stack([*full,valid,*inside,land_valid_ratio,lf]).astype('float32')


def discover_source_tiles(path):
    import rasterio
    from rasterio.warp import transform_bounds
    root=pathlib.Path(path)
    files=sorted(root.rglob('*.tif'))
    if not files:raise FileNotFoundError('No downloaded ESA 2021 v200 native TIFFs in '+str(root))
    found=[]
    for p in files:
        try:
            with rasterio.open(p) as ds:
                if ds.count<1 or not ds.crs:continue
                # Source may be geographic; transformed bounds only for indexing,
                # not as a geometry replacement at high latitudes.
                b=transform_bounds(ds.crs,'EPSG:6933',*ds.bounds,densify_pts=31)
                found.append({'path':str(p.resolve()),'bounds':[float(x) for x in b],
                              'width':ds.width,'height':ds.height,'count':ds.count,
                              'crs':str(ds.crs)})
        except Exception as exc:
            raise RuntimeError(f'Invalid WorldCover TIFF {p}: {exc}') from exc
    if not found:raise ValueError('No readable WorldCover source COGs')
    return found

def _overlap(a,b):
    return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]

def rasterise_source(tiles,bounds,n,px_per_cell=PPC):
    """Warp ESA categorical COG only ONCE per overlapping source tile.

    GDAL nearest neighbour in an equal-area 10m lattice preserves original
    class labels, but raster sampling is not exact polygon/pixel intersection.
    """
    import rasterio
    from rasterio.warp import reproject,Resampling
    from affine import Affine
    shape=n*px_per_cell
    res=10000/px_per_cell
    affine=Affine(res,0,bounds[0],0,-res,bounds[3])
    out=np.zeros((shape,shape),dtype=np.uint8)
    hits=[z for z in tiles if _overlap(z['bounds'],bounds)]
    for item in hits:
        with rasterio.open(item['path']) as ds:
            if ds.count!=1:raise ValueError('Expected ESA WorldCover 1-band Map source '+item['path'])
            reproject(source=rasterio.band(ds,1),destination=out,
                src_transform=ds.transform,src_crs=ds.crs,
                src_nodata=ds.nodata if ds.nodata is not None else 0,
                dst_transform=affine,dst_crs='EPSG:6933',dst_nodata=0,
                resampling=Resampling.nearest,init_dest_nodata=False,
                num_threads=2)
    if np.any((out!=0)&~np.isin(out,WC_CODES)):
        raise ValueError('Unexpected ESA 2021 classification values in source COG')
    return out,affine,len(hits)

def compute_land_mask(shapefiles,bounds,transform,n,px_per_cell=PPC,expected=None):
    import rasterio.features
    import shapely.geometry
    import shapely
    from pyproj import Transformer
    geom,area=coast.prepare_land_tile(shapefiles,bounds,expected)
    if area==0:return np.zeros((n*px_per_cell,n*px_per_cell),dtype=np.uint8),area
    ll=shapely.geometry.shape(geom)
    to_eq=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    eq=shapely.transform(ll,to_eq.transform,interleaved=False)
    mask=rasterio.features.rasterize([(eq,1)],out_shape=(n*px_per_cell,n*px_per_cell),
                transform=transform,fill=0,dtype=np.uint8,all_touched=False)
    return mask,area

def check_land_area(block,frame,tol=0.01):
    n=block.shape[1];f=frame.set_index(['grid_x','grid_y'])
    bad=[];errors=[]
    # y ascending in GF10; raster rows are north -> south.
    for row in range(n):
        for col in range(n):
            x=int(frame.attrs['x0'])+col
            y=int(frame.attrs['y0'])+n-row-1
            if (x,y) not in f.index:continue # Ocean: not a GF10 land ID.
            target=float(f.loc[(x,y),'land_area_km2'])/100
            got=float(block[24,row,col]);e=abs(target-got)
            errors.append(e)
            if e>tol:bad.append({'grid_id':f'{x}_{y}','vector_land':target,'raster_land':got,'abs_error':e})
    if bad:raise ValueError('Native 10m GSHHG coastal area mismatch: '+str(bad[:4]))
    return float(max(errors,default=0.0))

def write_tile(path,block,x0,y0,n):
    import rasterio
    from affine import Affine
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        # Do not silently overwrite previous source input or scientific run.
        raise FileExistsError(f'Immutable completed tile output: {p}')
    tmp=p.with_name(p.name+'.writing')
    aff=Affine(10000,0,x0*10000,0,-10000,(y0+n)*10000)
    with rasterio.open(tmp,'w',driver='GTiff',width=n,height=n,count=25,
                       dtype='float32',crs='EPSG:6933',transform=aff,
                       compress='DEFLATE',predictor=3,nodata=-9999) as ds:
        for i,name in enumerate(contract.WC_BANDS,1):
            arr=block[i-1];ds.write(np.where(np.isfinite(arr),arr,-9999).astype('float32'),i)
            ds.set_band_description(i,name)
    os.replace(tmp,p)
    return qc.check_raster(p,'worldcover',x0,y0,n,expected_manifest=contract.WC_BANDS)

def one_tile(task,tiles,gshhg,grid_file,out,px_per_cell=PPC):
    import pandas as pd
    x,y,n=(int(task[k]) for k in ('tile_x0','tile_y0','tile_size'))
    if n!=5:raise ValueError('WorldCover GEE Gate C and local method use 5x5 blocks')
    target=pathlib.Path(out)/f'wc_local_{x}_{y}_{n}.tif'
    audit=target.with_suffix('.qc.json')
    if target.exists():
        if not audit.exists():raise FileExistsError('Existing tile lacks source QC; investigate '+str(target))
        result=qc.check_raster(target,'worldcover',x,y,n,expected_manifest=contract.WC_BANDS)
        return {'status':'REUSED','tile':str(target),**result}
    bounds=grid.tile_bounds(x,y,n)
    if isinstance(grid_file,pd.DataFrame) and {'grid_x','grid_y'}==set(grid_file.index.names):
        keys=[(i,j) for i in range(x,x+n) for j in range(y,y+n)]
        g=grid_file.reindex(keys).dropna(subset=['land_area_km2']).reset_index()
    else:
        g=(grid_file if isinstance(grid_file,pd.DataFrame) else
           pd.read_parquet(grid_file,columns=['grid_id','grid_x','grid_y','land_area_km2']))
        g=g[g.grid_x.between(x,x+n-1)&g.grid_y.between(y,y+n-1)].copy()
    if len(g)==0:raise ValueError('Non-land tile in plan')
    g.attrs['x0']=x;g.attrs['y0']=y
    src,aff,num_sources=rasterise_source(tiles,bounds,n,px_per_cell)
    mask,measured=compute_land_mask(gshhg,bounds,aff,n,px_per_cell,float(g.land_area_km2.sum()))
    outval=aggregate_categories(src,mask,px_per_cell)
    coast_error=check_land_area(outval,g)
    report=write_tile(target,outval,x,y,n)
    report.update({'status':'PASS_NATIVE10M_NEAREST_WARP_VALIDATED','source_files':num_sources,
                   'gshhg_vector_land_km2':measured,'max_cell_land_area_difference':coast_error,
                   'method':'One native categorical warp to 10m equal-area lattice; not exact source pixel overlay',
                   'land_fraction_tolerance':0.01})
    audit.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return report

_CTX={}

def _worker_init(tiles,gshhg_root,grid_path,out):
    global _CTX
    _CTX={'tiles':tiles,'gpaths':coast.discover_gshhg(gshhg_root),
          'grid':grid.read_grid(grid_path).set_index(['grid_x','grid_y']).sort_index(),
          'out':out}

def _worker_run(rec):
    ctx=_CTX
    return one_tile(rec,ctx['tiles'],ctx['gpaths'],ctx['grid'],ctx['out'])

def main(argv=None):
    p=argparse.ArgumentParser(description='Local ESA COG WorldCover 2021-> GF10 25 bands, no GEE EECU')
    p.add_argument('--source',required=True,help='Directory with official 2021 v200 map COG TIFFs')
    p.add_argument('--grid',required=True,help='Frozen 1,395,471-row GF10 parquet')
    p.add_argument('--gshhg',required=True,help='GSHHG Full L1-L4 source root')
    p.add_argument('--plan',required=True,help='Frozen 5x5 WorldCover tile CSV')
    p.add_argument('--out',required=True)
    p.add_argument('--limit',type=int,default=0,help='0 means full plan; positive limit is only for QC')
    p.add_argument('--workers',type=int,default=16,help='Windows processes; each GDAL warp uses up to 2 threads. Start 16/24, benchmark I/O.')
    args=p.parse_args(argv)
    import pandas as pd
    plan=pd.read_csv(args.plan)
    if set(plan.family)!= {'worldcover'} or not plan.tile_size.eq(5).all():
        raise ValueError('Not a frozen WorldCover 5x5 plan')
    if args.limit<0:raise ValueError('Invalid limit')
    if not 1<=args.workers<=48:raise ValueError('Workers range 1..48; Windows process limit and 128GB RAM guard')
    if args.limit:plan=plan.iloc[:args.limit]
    tiles=discover_source_tiles(args.source)
    gpaths=coast.discover_gshhg(args.gshhg)
    # Immutable input fingerprint for resumable 55k-tile production. Do not
    # re-use previous tile outputs against different raw source or coastline.
    out_path=pathlib.Path(args.out);out_path.mkdir(parents=True,exist_ok=True)
    sources=[(z['path'],pathlib.Path(z['path']).stat().st_size,pathlib.Path(z['path']).stat().st_mtime_ns) for z in tiles]
    coast_src=[(str(v),v.stat().st_size,v.stat().st_mtime_ns) for v in gpaths.values()]
    inputs={'sources':sources,'gshhg':coast_src,'gf10':str(pathlib.Path(args.grid).resolve()),
            'gf10_stat':[pathlib.Path(args.grid).stat().st_size,pathlib.Path(args.grid).stat().st_mtime_ns],
            'method':'local_equal_area_10m_nearest_20261105'}
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    contract_path=out_path/'immutable_sources.json'
    if contract_path.is_file():
        prior=json.loads(contract_path.read_text(encoding='utf8'))
        if prior['fingerprint']!=fingerprint:raise FileExistsError('Immutable input source fingerprint changed. Do not reuse prior tiles.')
    else:
        if list(out_path.glob('wc_local_*.tif')):raise FileExistsError('Already has tiles but no source registry')
        contract_path.write_text(json.dumps({'fingerprint':fingerprint,'n_cog':len(tiles),
                     'n_gshhg':len(gpaths),'method':inputs['method']},indent=2),encoding='utf8')
    # Read the immutable GF10 reference only ONCE for tens of thousands of tiles.
    out=[];bad=[]
    tasks=plan.to_dict('records')
    if args.workers==1:
        _worker_init(tiles,args.gshhg,args.grid,args.out)
        iterator=((r,_worker_run(r)) for r in tasks)
        try:
            for r,result in iterator:
                out.append(result);print('DONE',r['tile_key'],flush=True)
        except Exception as exc:
            bad.append({'tile':r['tile_key'],'error':repr(exc),'traceback':traceback.format_exc()})
    else:
        # Process (rather than thread) pools isolate GDAL cache and allow
        # parallel native 10m warps. Each worker loads the 1.395m-row
        # read-only GF10 index only once, not once per 5x5 tile.
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers,initializer=_worker_init,
            initargs=(tiles,args.gshhg,args.grid,args.out)) as pool:
            futures={pool.submit(_worker_run,r):r for r in tasks}
            for fut in concurrent.futures.as_completed(futures):
                r=futures[fut]
                try:
                    result=fut.result();out.append(result)
                    print('DONE',r['tile_key'],flush=True)
                except Exception as exc:
                    bad.append({'tile':r['tile_key'],'error':repr(exc)})
                    for other in futures:
                        if not other.done():other.cancel()
                    break
    pathlib.Path(args.out).mkdir(parents=True,exist_ok=True)
    (pathlib.Path(args.out)/'run_state.json').write_text(json.dumps({'complete':not bad and len(out)==len(plan),'n_finished':len(out),'n_required':len(plan),'errors':bad,'source':args.source,'method':'LOCAL_NATIVE_10M_APPROX'},indent=2),encoding='utf8')
    if bad:raise SystemExit(2)

if __name__=='__main__':main()
