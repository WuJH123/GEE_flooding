"""Stable entrypoint for server PowerShell wrappers."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='CEE GF10 local-all-data v1.2 (no GitHub connection)')
    p.add_argument('--root',default=r'E:\WJH_CEE')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('inventory')
    sub.add_parser('gmted-audit')
    sub.add_parser('grid-tiles')
    stage=sub.add_parser('stage');stage.add_argument('--family',required=True,
         choices=['worldclim','era5ex','admin','ucdb','hydroatlas','roads','gisd']);
    stage.add_argument('--first',type=int);stage.add_argument('--cap-gb',type=float,default=45)
    raster=sub.add_parser('raster')
    raster.add_argument('--family',required=True,choices=['gmted','worldclim-bio','worldclim-monthly','grip-density'])
    raster.add_argument('--workers',type=int,default=8);raster.add_argument('--max-tiles',type=int,default=12)
    raster.add_argument('--max-sources',type=int,default=1);raster.add_argument('--source')
    era=sub.add_parser('era5ex');era.add_argument('--years',default='2021,2022,2023')
    era.add_argument('--max-vars',type=int,default=1);era.add_argument('--max-rows',type=int)
    gis=sub.add_parser('gisd');gis.add_argument('--workers',type=int,default=8)
    gis.add_argument('--max-sources',type=int,default=3)
    gis2=sub.add_parser('gisd-combine');gis2.add_argument('--allow-partial',action='store_true')
    inspect=sub.add_parser('vector-inspect');inspect.add_argument('--source',required=True)
    link=sub.add_parser('vector-link');link.add_argument('--source',required=True)
    link.add_argument('--layer',required=True);link.add_argument('--fields',required=True)
    link.add_argument('--tag',required=True);link.add_argument('--max-cells',type=int)
    sub.add_parser('flood-catalogue')
    merge=sub.add_parser('assemble');merge.add_argument('--include-optional',action='store_true')
    merge.add_argument('--allow-pilot',action='store_true')
    annual=sub.add_parser('merge-year');annual.add_argument('--year',type=int,required=True)
    sub.add_parser('status')
    a=p.parse_args();root=Path(a.root)
    if a.command=='inventory':
        from .inventory import inventory
        v=inventory(root/'CEE数据',root/'reports/cee_all_inventory_v11.csv')
    elif a.command=='gmted-audit':
        from .source_audit import gmted_audit
        v=gmted_audit(root)
    elif a.command=='grid-tiles':
        from .grid import tiles
        v=tiles(root)
    elif a.command=='stage':
        from .staging import stage_family
        v=stage_family(root/'CEE数据',root/'data/staged/cee_all',a.family,cap_gb=a.cap_gb,first=a.first)
    elif a.command=='raster':
        from .raster import candidates,run
        paths=[Path(a.source)] if a.source else candidates(root,a.family)
        if not paths:raise FileNotFoundError('No input raster, stage ZIP or check local names')
        if a.max_sources is not None and a.max_sources>0:paths=paths[:a.max_sources]
        v=[run(root,a.family,x,workers=a.workers,max_tiles=(a.max_tiles or None)) for x in paths]
    elif a.command=='era5ex':
        from .era import run
        years=[int(x) for x in a.years.split(',')]
        v=run(root,years=years,max_vars=(a.max_vars or None),max_rows=a.max_rows)
    elif a.command=='gisd':
        from .gisd import run
        v=run(root,workers=a.workers,max_sources=(a.max_sources or None))
    elif a.command=='gisd-combine':
        from .gisd import combine
        v=combine(root,require_953=not a.allow_partial)
    elif a.command=='vector-inspect':
        from .vector import inspect
        v=inspect(a.source)
    elif a.command=='vector-link':
        from .vector import centroid_link
        v=centroid_link(root,a.source,a.layer,a.fields.split(','),a.tag,a.max_cells)
    elif a.command=='flood-catalogue':
        from .observations import read_flood_catalogue
        v=read_flood_catalogue(root)
    elif a.command=='assemble':
        from .assemble import collect
        v=collect(root,include_optional=a.include_optional,allow_pilot=a.allow_pilot)
    elif a.command=='merge-year':
        from .assemble import merge_year
        v=merge_year(root,a.year)
    elif a.command=='status':
        from .status import report
        v=report(root)
    print(json.dumps(v,ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
