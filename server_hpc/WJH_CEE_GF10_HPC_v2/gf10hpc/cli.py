"""Entry point: python -m gf10hpc <command> [options]."""
import argparse,json,sys
from pathlib import Path
from . import __version__

def main(argv=None):
    a=argparse.ArgumentParser(description='GF10 nonantarctic local CPU data factory v2')
    a.add_argument('--root',default=r'E:\WJH_CEE')
    sub=a.add_subparsers(dest='command',required=True)
    p=sub.add_parser('audit',help='Read-only verify frozen GF10 and report')
    p.add_argument('--grid');p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('inventory',help='Scan all already-downloaded source files (no download)')
    p.add_argument('--out')
    p=sub.add_parser('tiles',help='Index 10km grid into tiles once')
    p.add_argument('--grid');p.add_argument('--out');p.add_argument('--side',type=int,default=64)
    p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('stage',help='Extract only a selected ZIP member; no full archive unzip')
    p.add_argument('--zip',required=True);p.add_argument('--member',required=True)
    p.add_argument('--out',required=True)
    p=sub.add_parser('stage-archive',help='Safely expand small ZIP archive into new version directory')
    p.add_argument('--zip',required=True);p.add_argument('--out',required=True)
    p.add_argument('--max-gb',type=float,default=20)
    p=sub.add_parser('raster-fast',help='CPU parallel GDAL 1km aligned reduction, APPROXIMATION')
    p.add_argument('--tiles',required=True)
    s=p.add_mutually_exclusive_group(required=True)
    s.add_argument('--source',nargs='+');s.add_argument('--source-dir')
    p.add_argument('--glob',default='*.tif');p.add_argument('--profile',required=True)
    p.add_argument('--out',required=True);p.add_argument('--workers',type=int,default=24)
    p.add_argument('--gdal-threads',type=int,default=2)
    p.add_argument('--max-tiles',type=int)
    p=sub.add_parser('raster-exact',help='Native-pixel area overlap using C++ exactextract + parallel Windows processes')
    p.add_argument('--tiles',required=True)
    s=p.add_mutually_exclusive_group(required=True)
    s.add_argument('--source',nargs='+');s.add_argument('--source-dir')
    p.add_argument('--glob',default='*.tif');p.add_argument('--profile',required=True)
    p.add_argument('--out',required=True);p.add_argument('--workers',type=int,default=16)
    p.add_argument('--max-tiles',type=int)
    p=sub.add_parser('gisd-prep',help='Recode GISD30 native 0..8 into 2000 and 2020 binary fractions before reprojection')
    p.add_argument('--source-dir',required=True);p.add_argument('--out',required=True)
    p.add_argument('--workers',type=int,default=8);p.add_argument('--gdal-threads',type=int,default=2)
    p.add_argument('--max-files',type=int)
    p=sub.add_parser('era5ex',help='Sample existing annual netCDF in its 0.1degree resolution')
    p.add_argument('--source',required=True);p.add_argument('--variable',default='auto')
    p.add_argument('--grid');p.add_argument('--out',required=True)
    p.add_argument('--years',nargs='+',type=int,default=[2000,2005,2010,2015,2020,2021,2022,2023,2024,2025])
    p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('vector-centroid',help='Assign by GF10 centre only (not fractional land area)')
    p.add_argument('--source',required=True);p.add_argument('--layer')
    p.add_argument('--field',required=True);p.add_argument('--extra',nargs='*',default=[])
    p.add_argument('--grid');p.add_argument('--out',required=True)
    p.add_argument('--batch',type=int,default=100000);p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('assemble',help='Merge checked raster-static products into one GF10 wide table')
    p.add_argument('--grid');p.add_argument('--product',action='append',required=True)
    p.add_argument('--out',required=True);p.add_argument('--pilot',action='store_true')
    p=sub.add_parser('exact-qa',help='Compare one fast source tile against native exactextract')
    p.add_argument('--source',required=True);p.add_argument('--grid-tile',required=True)
    p.add_argument('--fast-tile',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--out',required=True);p.add_argument('--max-cells',type=int,default=500)
    p=sub.add_parser('verify-source',help='Audit actual TIFF metadata, native units and official dataset contracts')
    p.add_argument('--source',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--out',required=True)
    p=sub.add_parser('profiles',help='List explicit physical units and epoch for each supported source')
    args=a.parse_args(argv)
    root=Path(args.root);grid=str(root/'gf10_global_nonantarctic_land.parquet')
    if args.command=='audit':
        from .core import audit_grid
        answer=audit_grid(args.grid or grid,not args.pilot)
    elif args.command=='inventory':
        from .sources import inventory
        answer=inventory(root,args.out or str(root/'reports'/'hpc_sources_v2.csv'))
    elif args.command=='tiles':
        from .core import tile_index
        answer=tile_index(args.grid or grid,args.out or root/'data/working/gf10_hpc_tiles64_v2',args.side,not args.pilot)
    elif args.command=='stage':
        from .sources import stage_one
        answer=stage_one(args.zip,args.member,args.out)
    elif args.command=='stage-archive':
        from .sources import stage_archive
        answer=stage_archive(args.zip,args.out,args.max_gb)
    elif args.command=='raster-fast':
        from .raster import run
        sources=args.source if args.source else sorted(str(x) for x in Path(args.source_dir).rglob(args.glob))
        answer=run(args.tiles,sources,args.profile,args.out,args.workers,args.gdal_threads,10,args.max_tiles)
    elif args.command=='raster-exact':
        from .exact import run
        sources=args.source if args.source else sorted(str(x) for x in Path(args.source_dir).rglob(args.glob))
        answer=run(args.tiles,sources,args.profile,args.out,args.workers,args.max_tiles)
    elif args.command=='gisd-prep':
        from .gisd import run
        answer=run(args.source_dir,args.out,args.workers,args.gdal_threads,args.max_files)
    elif args.command=='era5ex':
        from .era import extract
        answer=extract(args.source,args.grid or grid,args.out,args.variable,args.years,args.pilot)
    elif args.command=='vector-centroid':
        from .vector import assign
        answer=assign(args.grid or grid,args.source,args.out,args.field,args.layer,args.extra,args.batch,args.pilot)
    elif args.command=='assemble':
        from .assemble import assemble
        answer=assemble(args.grid or grid,args.product,args.out,args.pilot)
    elif args.command=='exact-qa':
        from .qa_exact import compare
        answer=compare(args.source,args.grid_tile,args.fast_tile,args.profile,args.out,args.max_cells)
    elif args.command=='verify-source':
        from .verify import verify_source
        answer=verify_source(args.source,args.profile,args.out)
    else:
        from .raster import PROFILES
        answer=PROFILES
    print(json.dumps(answer,indent=2,ensure_ascii=False,default=str))
    return answer
