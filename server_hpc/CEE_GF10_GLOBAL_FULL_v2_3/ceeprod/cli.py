from __future__ import annotations
import argparse,json
from pathlib import Path


def main(argv=None):
    p=argparse.ArgumentParser(description='CEE GF10 v2 all-35-local-files unattended global CPU/GDB pipeline')
    p.add_argument('--root',default=r'E:\WJH_CEE')
    s=p.add_subparsers(dest='command',required=True)
    for name in ('plan','doctor','stage','verify','run','raster','vector','era5ex','gisd30','attributes','groundsource','assemble','geometry-cache','verify-providers'):
        sub=s.add_parser(name)
        if name=='doctor':sub.add_argument('--test-rar',action='store_true')
        if name=='stage':sub.add_argument('--family',choices=('worldclim','era5ex','admin','ucdb','hydroatlas','roads','gisd'))
        if name=='run':
            sub.add_argument('--raster-jobs',type=int,default=4)
            sub.add_argument('--raster-workers',type=int,default=16)
            sub.add_argument('--vector-jobs',type=int,default=2)
            sub.add_argument('--vector-workers',type=int,default=16)
            sub.add_argument('--stage-only',action='store_true')
        if name=='raster':
            sub.add_argument('--raster-jobs',type=int,default=4)
            sub.add_argument('--raster-workers',type=int,default=16)
        if name=='vector':
            sub.add_argument('--vector-jobs',type=int,default=2)
            sub.add_argument('--vector-workers',type=int,default=16)
        if name=='attributes':sub.add_argument('--family',choices=('admin0','admin1','ucdb','basin'))
        if name=='verify':sub.add_argument('--strict',action='store_true')
    a=p.parse_args(argv)
    root=Path(a.root)
    if a.command=='plan':
        from .runner import plan;res=plan(root)
    elif a.command=='verify-providers':
        from .discover import discover_all
        from .shared import write_json
        res=discover_all(root)
        write_json(root/'reports/cee_full_v2/vector_source_autodetect_v22.json',res)
        if res['errors']:
            raise ValueError('Required source providers are still unavailable: '+str(res['errors']))
    elif a.command=='stage':
        from .runner import stage;res=stage(root,only_family=a.family)
    elif a.command=='doctor':
        from .doctor import diagnose;res=diagnose(root,test_rar=a.test_rar)
    elif a.command=='run':
        from .runner import run_all;res=run_all(root,a.raster_jobs,a.raster_workers,a.vector_jobs,a.vector_workers,a.stage_only)
    elif a.command=='raster':
        from .runner import rasters;res=rasters(root,a.raster_jobs,a.raster_workers)
    elif a.command=='vector':
        from .runner import vectors;res=vectors(root,a.vector_jobs,a.vector_workers)
    elif a.command=='geometry-cache':
        from .gridcache import prepare;res=prepare(root)
    elif a.command=='era5ex':
        from .era_wide import run;res=run(root)
    elif a.command=='gisd30':
        from .gisd_history import run;res=run(root)
    elif a.command=='attributes':
        from .source_attributes import run
        res={fam:run(root,fam) for fam in ((a.family,) if a.family else ('admin0','admin1','ucdb','basin'))}
    elif a.command=='groundsource':
        from .observations_full import run;res=run(root)
    elif a.command=='assemble':
        from .assemble_full import run;res=run(root)
    elif a.command=='verify':
        from .quality import summarize;res=summarize(root,strict=a.strict)
    print(json.dumps(res,indent=2,ensure_ascii=False,default=str))
    return res
if __name__=='__main__':main()
