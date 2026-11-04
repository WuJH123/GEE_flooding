"""Free-EECU, native 10m ESA WorldCover 2021 to frozen equal-area GF10.

Native source = 2,651 public ESA COG Map tiles (~117 GB). Streamed 10m
EPSG6933 nearest-neighbour reprojection to 10m target *on the exact GF10
lattice*, followed by 10m-area category totals and GSHHG coastline masks.
NOT an exact original 4326 source pixel-overlap integral: independent Gate C
comparison on urban, coastal, ice and mangrove areas is a HARD publication gate.
"""
from __future__ import annotations
import contextlib,json,math,os,sys,traceback
from pathlib import Path
import numpy as np
from .base import WC_FIELDS,WC_CLASSES,atomic_json,load_json,sha256,check_output_identity

NATIVE=10
GF10_SIZE=10000
CLASS_SET=set(WC_CLASSES)
_WORKER=None

def source_index(source_dir,out,strict_full=False):
    """Headers only; no 117GB full data scan, no network/GEE activity."""
    from rasterio.warp import transform_bounds
    import rasterio
    root=Path(source_dir)
    if not root.is_dir():raise FileNotFoundError(root)
    tif=sorted(list(root.rglob('*.tif'))+list(root.rglob('*.tiff')))
    if not tif:raise FileNotFoundError('No ESA WorldCover Map COG files in '+str(root))
    items=[];total=0
    for i,p in enumerate(tif):
        with rasterio.open(p) as src:
            if src.count!=1:raise ValueError(f'{p}: WorldCover Map must contain one class band, not InputQuality')
            if src.crs is None or not src.crs.is_geographic:
                raise ValueError(f'{p}: official WorldCover source must be EPSG:4326 geographic')
            if src.res[0]<=0 or src.res[1]<=0:raise ValueError('Invalid source pixel transform')
            bb=transform_bounds(src.crs,'EPSG:6933',*src.bounds,densify_pts=41)
            if not all(np.isfinite(bb)):raise ValueError('Invalid projected source envelope '+str(p))
            stat=p.stat();total+=stat.st_size
            items.append({'name':str(p.resolve()),'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,
                          'bounds_6933':[float(z) for z in bb], 'bounds_lonlat':list(map(float,src.bounds)),
                          'native_resolution_degrees':[float(z) for z in src.res],
                          'crs':src.crs.to_string()})
    # Official ESA says 2,651 map tiles; do not pass FULL if list is partial.
    if strict_full and len(items)!=2651:
        raise ValueError(f'Expected 2651 official WorldCover 2021 Map COGs, found {len(items)}; no global completion allowed')
    out=Path(out)
    atomic_json(out,{'source':'ESA WorldCover v200 2021 Map','source_directory':str(root.resolve()),
                     'n_files':len(items),'total_bytes':total,'items':items,
                     'all_2651_tiles_present':len(items)==2651,
                     'process_note':'10m nearest reproject to EPSG6933 GF10 target; rasterized GSHHG L1-L4 true land; compare independent Gate C before full'})
    return {'files':len(items),'GB':round(total/1e9,3),'index_file':str(out)}

def pixel_summary(class_pixels,land_mask):
    """GF10 area fractions on a 10m equal-area raster (not raw lon/lat means)."""
    arr=np.asarray(class_pixels)
    land=np.asarray(land_mask,dtype=bool)
    if arr.shape!=land.shape or arr.ndim!=2:raise ValueError('2D source and land arrays must align')
    tot=arr.size
    # Two bincount passes instead of scanning 11 masks separately.
    # COG Map pixel codes are uint8; reject all unexpected nonzero codes.
    if arr.dtype.kind not in 'iu' or arr.min()<0 or arr.max()>255:
        raise ValueError('WorldCover Map should contain uint8 class codes')
    all_counts=np.bincount(arr.ravel().astype(np.uint8),minlength=256)
    land_counts=np.bincount(arr[land].ravel().astype(np.uint8),minlength=256)
    other=[int(i) for i in np.flatnonzero(all_counts) if i not in CLASS_SET and i!=0]
    if other:raise ValueError(f'Unknown WorldCover codes {other[:16]} - stop instead of inventing classes')
    n=int(sum(all_counts[c] for c in WC_CLASSES))
    L=int(np.count_nonzero(land))
    n_land=int(sum(land_counts[c] for c in WC_CLASSES))
    result={}
    for c in WC_CLASSES:
        count=int(all_counts[c])
        count_land=int(land_counts[c])
        result[f'wc_{c}_fraction_fullcell']=float(count/tot) if n else float('nan')
        result[f'wc_{c}_fraction_land']=float(count_land/L) if L and n_land else float('nan')
    result['wc_valid_fraction_fullcell']=n/tot
    result['wc_valid_fraction_land']=float(n_land/L) if L else float('nan')
    result['wc_gshhg_land_fraction_raster']=L/tot
    if n:
        assert abs(sum(result[f'wc_{c}_fraction_fullcell'] for c in WC_CLASSES)-n/tot)<2e-8
    if L and n_land:
        assert abs(sum(result[f'wc_{c}_fraction_land'] for c in WC_CLASSES)-n_land/L)<2e-8
    return result

def derived_fractions(stats):
    """Pure local arithmetic, no extra source/GEE time. Distinct class sets."""
    combinations={'vegetation':(10,20,30),'wetland':(90,95),
                  'built':(50,),'water':(80,),
                  'bluegreen':(10,20,30,90,95,80)}
    for denominator,tag in [('fullcell','fullcell'),('land','land')]:
        for name,codes in combinations.items():
            values=[stats[f'wc_{c}_fraction_{denominator}'] for c in codes]
            stats[f'wc_{name}_fraction_{tag}']=float(sum(values)) if all(np.isfinite(values)) else float('nan')
    return stats


def default_paths(root):
    root=Path(root)
    return {'tifs':root/'data'/'raw'/'esa_worldcover_2021'/'map',
            'index':root/'reports'/'worldcover_2021_source_index.json',
            'out':root/'data'/'derived'/'gf10_worldcover2021_native10m_v3'}

def block_plan(g,block=10):
    if block<1 or block>20:raise ValueError('For local 10m work use 1..20 GF10 cells per side')
    import pandas as pd
    tx=np.floor_divide(g.grid_x.to_numpy(),block)*block
    ty=np.floor_divide(g.grid_y.to_numpy(),block)*block
    x=g[['grid_id','grid_x','grid_y','land_area_km2']].copy()
    x['bx']=tx;x['by']=ty
    return x

def file_candidates(items,bounds):
    xmin,ymin,xmax,ymax=bounds
    return [a for a in items if not (a['bounds_6933'][2]<xmin or
                    a['bounds_6933'][0]>xmax or a['bounds_6933'][3]<ymin or a['bounds_6933'][1]>ymax)]

def _worker_init(index,gshhg,output_dir,pixel_m,product_hash,grid_hash):
    global _WORKER
    _WORKER={'index':index,'gshhg':gshhg,'out':Path(output_dir),
             'pixel_m':pixel_m,'product_hash':product_hash,'grid_hash':grid_hash}

def _block_compute(payload):
    """One 10x10 GF10 region; preserve all successfully committed shards on failure."""
    import rasterio
    import pandas as pd
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from rasterio.windows import Window
    from shapely.geometry import box,shape
    from shapely import transform as shapely_transform
    from pyproj import Transformer
    from ceeprodgee.coast import prepare_land_tile
    w=_WORKER
    bx,by,bsize,records=payload
    out=w['out'];name=f'part_{bx}_{by}_{bsize}'
    dest=out/'tiles'/(name+'.parquet');qcpath=out/'qc'/(name+'.json')
    srcqc=load_json(qcpath)
    if srcqc and dest.exists() and srcqc.get('status')=='OK' and srcqc.get('product_hash')==w['product_hash']:
        import pyarrow.parquet as pq
        if pq.ParquetFile(dest).metadata.num_rows==len(records):
            return {'block':name,'status':'REUSED','n':len(records)}
    if dest.exists() or qcpath.exists():
        raise FileExistsError('Incomplete/mismatched shard left from interrupted task; examine before overwriting: '+str(dest))
    from ceeprodgee.grid import tile_bounds
    bounds=tile_bounds(bx,by,bsize)
    sources=file_candidates(w['index']['items'],bounds)
    expected=sum(float(z[3]) for z in records)
    # Exact source polygons L1-L4; their 10m rasterized area may differ slightly.
    geo,llarea=prepare_land_tile(w['gshhg'],bounds,expected_land_km2=expected)
    to_equal=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    land=shapely_transform(shape(geo),to_equal.transform,interleaved=False)
    n=int(GF10_SIZE//w['pixel_m'])
    if n*w['pixel_m']!=GF10_SIZE:raise ValueError('pixel_m must divide 10km exactly')
    dst=Affine(w['pixel_m'],0,bx*GF10_SIZE,0,-w['pixel_m'],(by+bsize)*GF10_SIZE)
    rows=[];land_errors=[];not_covered=0
    with contextlib.ExitStack() as stack:
        vrts=[]
        for src in sources:
            ds=stack.enter_context(rasterio.open(src['name']))
            vrt=stack.enter_context(WarpedVRT(ds,crs='EPSG:6933',transform=dst,
                               width=n*bsize,height=n*bsize,src_nodata=ds.nodata,
                               nodata=0,resampling=Resampling.nearest,
                               warp_mem_limit=128))
            vrts.append(vrt)
        for x,y,key,area in records:
            x=int(x);y=int(y)
            iy=by+bsize-1-y;ix=x-bx
            transform=dst*Affine.translation(ix*n,iy*n)
            rect=box(x*GF10_SIZE,y*GF10_SIZE,(x+1)*GF10_SIZE,(y+1)*GF10_SIZE)
            pixel_classes=np.zeros((n,n),dtype=np.uint8)
            window=Window(ix*n,iy*n,n,n)
            for vrt in vrts:
                incoming=vrt.read(1,window=window,masked=False)
                valid=np.isin(incoming,WC_CLASSES)
                # Adjacent ESA tiles should not disagree on overlapping valid pixels.
                clashes=valid&(pixel_classes!=0)&(pixel_classes!=incoming)
                if clashes.any():raise ValueError('Overlapping source ESA COGs have conflicting class codes')
                sel=valid&(pixel_classes==0)
                pixel_classes[sel]=incoming[sel]
            clipped=land.intersection(rect)
            landarray=rasterize([(clipped,1)],out_shape=(n,n),transform=transform,
                                 fill=0,dtype='uint8',all_touched=False) if not clipped.is_empty else np.zeros((n,n),dtype='uint8')
            metrics=derived_fractions(pixel_summary(pixel_classes,landarray))
            actual=float(metrics['wc_gshhg_land_fraction_raster'])
            delta=abs(actual-area/100)
            land_errors.append(delta)
            if delta>0.01:raise ValueError(f'Cell {x}_{y} GSHHG raster vs vector area error {delta:.6f}>0.01; freeze and QA')
            if metrics['wc_valid_fraction_fullcell']==0:not_covered+=1
            rows.append({'grid_id':f'{x}_{y}','grid_x':x,'grid_y':y,'land_area_km2':area,**metrics})
    if len(rows)!=len(records) or len({z['grid_id'] for z in rows})!=len(records):
        raise ValueError('Missing/duplicate GF10 output')
    frame=pd.DataFrame(rows)
    dest.parent.mkdir(parents=True,exist_ok=True);qcpath.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix('.writing')
    frame.to_parquet(tmp,index=False,compression='zstd')
    os.replace(tmp,dest)
    atomic_json(qcpath,{'status':'OK','product_hash':w['product_hash'],'grid_sha256':w['grid_hash'],
         'block':name,'n_cells':len(records),'coast_vector_area_km2':llarea,
         'max_abs_land_fraction_raster_minus_vector':max(land_errors,default=None),
         'n_cells_no_worldcover_source':not_covered,'n_source_cogs':len(sources),
         'algorithm':'10m equal-area nearest reproject + 10m rasterized GSHHG, not exact original source pixel overlap'})
    return {'block':name,'status':'WROTE','n':len(records)}

def run_blocks(grid,index_path,gshhg_root,output_dir,workers=12,block=10,pilot_blocks=0,full=False,pixel_m=10):
    import concurrent.futures
    from .base import sha256
    from ceeprodgee.coast import discover_gshhg
    import pandas as pd
    if full == bool(pilot_blocks):raise ValueError('Exactly one of --full or --pilot-blocks is required')
    if pixel_m!=10:raise ValueError('Formal v3 product requires genuine 10m rasterization; no silent downgrades')
    if workers<1 or workers>32:raise ValueError('Use 1..32 worker processes (benchmark SSD bottleneck)')
    index=load_json(index_path)
    if not index or index.get('source')!='ESA WorldCover v200 2021 Map':raise ValueError('Missing/wrong ESA source catalog')
    if full and not index.get('all_2651_tiles_present'):raise ValueError('Full world needs all 2651 official map source COGs')
    coast=discover_gshhg(gshhg_root)
    meta={'algorithm_version':'native10m_GSHHG_v3a','source_index_sha':sha256(index_path),
          'grid_file_sha':sha256(grid),'mask_pixel_m':pixel_m,'block_cells':block,
          'source_coast_files':{i:{'path':str(p),'size':p.stat().st_size,'mtime':p.stat().st_mtime_ns}
                                for i,p in coast.items()}}
    out=check_output_identity(output_dir,meta)
    from .base import load_gf10
    g=block_plan(load_gf10(grid,strict=True),block)
    if pilot_blocks:
        # Preregister pilot blocks: Wuhan, Mumbai, Iceland, Niger delta; no flood labels.
        ref=[(1102,372),(702,238),(-166,658),(57,52)]
        targets={(x//block*block,y//block*block) for x,y in ref[:pilot_blocks]}
        keep=np.zeros(len(g),dtype=bool)
        for xx,yy in targets:keep|=((g.bx==xx)&(g.by==yy)).to_numpy()
        g=g.loc[keep]
        if len(targets)!=pilot_blocks:raise ValueError('Pilot blocks collapsed unexpectedly')
    grouped=g.groupby(['bx','by'],sort=True)
    def payloads():
        for (bx,by),gg in grouped:
            records=[(int(z.grid_x),int(z.grid_y),str(z.grid_id),float(z.land_area_km2)) for z in gg.itertuples(index=False)]
            # _block_compute requires (x,y,key,area)
            yield (int(bx),int(by),block,records)
    counted={}
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers,initializer=_worker_init,
           initargs=(index,coast,str(out),pixel_m,sha256(out/'product_identity.json'),meta['grid_file_sha'])) as pool:
        for result in pool.map(_block_compute,payloads(),chunksize=1):
            counted[result['status']]=counted.get(result['status'],0)+1
            n=sum(counted.values())
            if n%25==0 or (pilot_blocks and n==pilot_blocks):
                print(f'WorldCover local 10m GF10: {n}/{len(grouped)} blocks, {counted}',flush=True)
    summary={'expected_blocks':len(grouped),'result_blocks':counted,
             'full_requested':full,'no_gee_eecu_used':True,
             'publication_ready':False,'note':'Run worldcover-verify + compare independent GEE Gate C TIFF before publication.'}
    atomic_json(out/'latest_run.json',summary)
    return summary

def read_tiles(out):
    import pandas as pd
    root=Path(out)/'tiles'
    files=sorted(root.glob('part_*.parquet'))
    if not files:raise FileNotFoundError('No audited WorldCover block results in '+str(root))
    return pd.concat([pd.read_parquet(p) for p in files],ignore_index=True),files

def compare_gate_c(out,reference_dir,report_file,minimum_cells=12):
    """Independent online Gate C, 4 x 10x10 reference TIFFs, each 25 bands.

    There is no exact equality claim: native 10m geographic-source warp to
    zero-origin 10m equal-area approximates true pixel overlap; reject local
    workflow when the deviation exceeds the pre-registered 1-ppt gate.
    """
    import rasterio
    from .base import WC_FIELDS
    reference=Path(reference_dir)
    label=('wuhan','mumbai','iceland','niger_delta')
    data,files=read_tiles(out)
    if data.grid_id.duplicated().any():raise ValueError('Duplicate GF10 from partial tiles')
    data=data.set_index('grid_id',verify_integrity=True)
    per_region=[]
    all_diffs=[]
    for k in label:
        p=reference/f'worldcover_{k}_10x10.tif'
        if not p.is_file():raise FileNotFoundError('Original independent Gate C mosaic required: '+str(p))
        with rasterio.open(p) as ds:
            if ds.count!=25 or ds.crs is None or ds.crs.to_epsg()!=6933 or ds.width!=10 or ds.height!=10:
                raise ValueError('Unexpected original Gate C reference metadata '+str(p))
            if abs(ds.res[0]-10000)>1e-5 or abs(ds.res[1]-10000)>1e-5:
                raise ValueError('Gate C GF10 must be 10km EPSG6933')
            arr=ds.read(masked=True).filled(np.nan)
            current_diffs=[];common=0
            for row in range(ds.height):
                for col in range(ds.width):
                    x=int(round((ds.transform*(col+0.5,row+0.5))[0]/10000-0.5))
                    y=int(round((ds.transform*(col+0.5,row+0.5))[1]/10000-0.5))
                    key=f'{x}_{y}'
                    if key not in data.index:continue
                    ref=arr[:,row,col]
                    cur=data.loc[key,list(WC_FIELDS)].to_numpy(dtype=np.float64)
                    good=np.isfinite(ref)&np.isfinite(cur)
                    if good.any():
                        current_diffs.extend(np.abs(ref[good]-cur[good]).tolist())
                        common+=1
            if common<minimum_cells:raise ValueError(f'Insufficient shared cells for Gate C {k}: {common}')
            all_diffs.extend(current_diffs)
            per_region.append({'name':k,'n_common_cells':common,'max_abs_fraction_diff':max(current_diffs),
                              'p95_abs_fraction_diff':float(np.percentile(current_diffs,95)),
                              'reference_sha256':sha256(p)})
    maxdiff=max(all_diffs);p95=float(np.percentile(all_diffs,95))
    result={'status':'PASS' if maxdiff<=0.01 and p95<=0.005 else 'FAIL_NEEDS_METHOD_REVIEW',
            'max_abs_fraction_diff':maxdiff,'p95_abs_fraction_diff':p95,
            'gate_max_tolerance':0.01,'gate_p95_tolerance':0.005,
            'n_reference_comparisons':len(all_diffs),'region_tests':per_region,
            'note':'Approximate 10m rasterization benchmark against original GEE 10m Gate C; independent remote sensing map accuracy not tested.'}
    atomic_json(report_file,result)
    if result['status']!='PASS':raise ValueError('WorldCover native local vs GEE Gate C did not pass. See '+str(report_file))
    return result

def verify_global(out,grid_path,require_full=True):
    import pandas as pd
    from .base import load_gf10,GRID_N,WC_FIELDS
    data,files=read_tiles(out)
    g=load_gf10(grid_path,strict=True)
    if data.grid_id.duplicated().any():raise ValueError('Duplicated GF10 output')
    found=set(data.grid_id.astype(str))
    source_ids=set(g.grid_id.astype(str))
    if not found.issubset(source_ids):raise ValueError('Results contain unknown GF10 IDs')
    if require_full and found!=source_ids:raise ValueError(f'Global product incomplete: {len(found)}/{GRID_N} cells')
    diffs=[];bad=[]
    for kind,fields,valid in [
       ('full',[f'wc_{c}_fraction_fullcell' for c in WC_CLASSES],'wc_valid_fraction_fullcell'),
       ('land',[f'wc_{c}_fraction_land' for c in WC_CLASSES],'wc_valid_fraction_land')]:
        ok=data[valid].notna()&data[fields[0]].notna()
        err=(data.loc[ok,fields].sum(axis=1)-data.loc[ok,valid]).abs()
        if (err>2e-5).any():bad.append(f'{kind} categorical non-conservation')
        diffs.append(float(err.max()) if len(err) else None)
    lerr=(data.wc_gshhg_land_fraction_raster-data.land_area_km2/100).abs()
    if (lerr>0.01).any():bad.append('GSHHG raster coastline mismatch')
    if data[list(WC_FIELDS)].select_dtypes(include='number').stack().gt(1+1e-5).any():
        bad.append('invalid land-cover fraction above 1')
    report={'n_frozen_gf10':len(g),'n_output_rows':len(data),'n_shards':len(files),
      'n_with_valid_worldcover':int(data.wc_valid_fraction_fullcell.gt(0).sum()),
      'n_with_land_coverage':int(data.wc_valid_fraction_land.gt(0).sum()),
      'all_frozen_grid_ids_present':found==source_ids,
      'max_class_sum_minus_valid_fraction':[v for v in diffs],
      'max_land_raster_vs_vector_difference':float(lerr.max()),
      'qa_errors':bad,'full_global_source_ready':found==source_ids and not bad,
      'note':'Source-coverage gaps remain NaN; this verifies structure and 10m aggregation, not WorldCover classification accuracy.'}
    atomic_json(Path(out)/'global_qa.json',report)
    if bad or (require_full and found!=source_ids):raise ValueError('Scientific QC failed; inspect '+str(Path(out)/'global_qa.json'))
    return report
