"""Dedicated independent CLI. Does not call GEE or old-project scripts."""
import argparse
from pathlib import Path
from .paths import ensure_structure

def parser():
    p=argparse.ArgumentParser(prog='gee-flooding',description='Independent urban flood ML research')
    p.add_argument('--root',type=Path,default=Path(r'E:\GEE_flooding'))
    commands=p.add_subparsers(dest='command',required=True)
    commands.add_parser('init',help='Create local data/outputs/reports dirs')
    commands.add_parser('download',help='Get original Groundsource from Zenodo, verify MD5')
    s=commands.add_parser('bootstrap-grid',help='Freeze GF10 2020 from two read-only SMOD TIFFs')
    s.add_argument('--west',type=Path,required=True)
    s.add_argument('--east',type=Path,required=True)
    s.add_argument('--urban-min',type=float,default=.001)
    s.add_argument('--valid-min',type=float,default=.95)
    s=commands.add_parser('labels',help='Project original polygons on frozen 2020 GF10 grid')
    s.add_argument('--raw',type=Path,required=True)
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--grid-qc',type=Path,required=True)
    s.add_argument('--batch-size',type=int,default=10000)
    s.add_argument('--start',default='2000-01-01')
    s.add_argument('--end',default='2025-12-31')
    s=commands.add_parser('panel',help='Combine complete storm exposures and static factors')
    s.add_argument('--weather',type=Path,required=True)
    s.add_argument('--static',type=Path,required=True)
    s.add_argument('--labels',type=Path,required=True)
    s=commands.add_parser('baseline',help='M0-M2 NEWS-REPORT proxy only, dual city+storm holdouts')
    s.add_argument('--panel',type=Path,required=True)
    s.add_argument('--seed',type=int,default=42)
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    root=ensure_structure(args.root)
    if args.command=='init':print('Project initialized:',root);return
    if args.command=='download':
        from .download import download_groundsource
        print(download_groundsource(root));return
    if args.command=='bootstrap-grid':
        from .grid import freeze
        print(freeze(root,args.west,args.east,args.urban_min,args.valid_min))
        return
    if args.command=='labels':
        from .labels import build_labels
        result=build_labels(root,args.raw,args.grid,args.grid_qc,args.batch_size,start=args.start,end=args.end)
    elif args.command=='panel':
        from .panel import assemble
        result=assemble(root,args.weather,args.static,args.labels)
    elif args.command=='baseline':
        from .train import run
        result=run(root,args.panel,args.seed)
    print(result)

if __name__=='__main__':main()
