"""Windows-first reproducible CLI. Default mode is READ-ONLY/DRY-RUN."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .base import frozen_grid,load_gf10
from .worldcover_local import default_paths,source_index,run_blocks,verify_global,compare_gate_c
from .cost import budget
from .gee_runner import (source_probe,merit_plan,merit_submit,merit_audit,merit_merge,
                          weather_plan,weather_submit,weather_audit,all_status,RUN_ID)


def main(argv=None):
    p=argparse.ArgumentParser(prog='python -m ceeopt',description='CEE GF10 official native-10m local land cover and EECU-bounded GEE')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--root',default=r'E:\WJH_CEE');d.add_argument('--site',choices=['server','gee'],default='server')
    a=sub.add_parser('cost');a.add_argument('--n-cells',type=int,default=1395471)
    a=sub.add_parser('wc-index');a.add_argument('--root',default=r'E:\WJH_CEE');a.add_argument('--input');a.add_argument('--full',action='store_true')
    a=sub.add_parser('wc-pilot');a.add_argument('--root',default=r'E:\WJH_CEE');a.add_argument('--workers',type=int,default=8)
    a=sub.add_parser('wc-compare');a.add_argument('--root',default=r'E:\WJH_CEE');a.add_argument('--reference-dir')
    a=sub.add_parser('wc-full');a.add_argument('--root',default=r'E:\WJH_CEE');a.add_argument('--workers',type=int,default=16);a.add_argument('--confirm')
    a=sub.add_parser('wc-verify');a.add_argument('--root',default=r'E:\WJH_CEE');a.add_argument('--partial',action='store_true')
    sub.add_parser('gee-probe')
    a=sub.add_parser('merit-plan');a.add_argument('--block',type=int,choices=[10,20],default=20)
    a=sub.add_parser('merit-pilot');a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('merit-next');a.add_argument('--block',type=int,choices=[10,20],default=20);a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('merit-audit');a.add_argument('--key',default='merit_1090_360_20');a.add_argument('--file')
    sub.add_parser('merit-merge')
    a=sub.add_parser('weather-plan');a.add_argument('--events',default='config/gf10_event_dates.parquet');a.add_argument('--block',type=int,default=50)
    a=sub.add_parser('weather-pilot');a.add_argument('--date',default='2023-06-01');a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('weather-next');a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('weather-audit');a.add_argument('--key',default='met_2023-06-01_1100_370_10');a.add_argument('--file')
    sub.add_parser('gee-status')
    args=p.parse_args(argv)
    cmd=args.command
    if cmd=='doctor':
        root=Path(args.root)
        if args.site=='server':
            ref=frozen_grid(root);g=load_gf10(ref)
            print(json.dumps({'status':'SERVER_GF10_FROZEN','n':len(g),'grid':str(ref),
                'worldcover_map_dir':str(default_paths(root)['tifs']),
                'GEE_used_by_this_command':False},ensure_ascii=False,indent=2))
        else:
            from .gee_runner import _root
            c=_root();g=load_gf10(c['gf10'])
            print(json.dumps({'status':'GEE_FROZEN_CONFIG_NO_TASKS','project':c['project'],
                              'n':len(g),'GF10':c['gf10'],'no_tasks_submitted':True},ensure_ascii=False,indent=2))
    elif cmd=='cost':print(json.dumps(budget(cells=args.n_cells),indent=2))
    elif cmd=='wc-index':
        paths=default_paths(args.root)
        print(json.dumps(source_index(args.input or paths['tifs'],paths['index'],strict_full=args.full),indent=2))
    elif cmd in ('wc-pilot','wc-full'):
        paths=default_paths(args.root)
        if cmd=='wc-full':
            if args.confirm!='GF10_LOCAL_10M_FULL_20261104':
                raise ValueError('To run complete 2651-tile native10m local processing, explicit --confirm GF10_LOCAL_10M_FULL_20261104 required')
            comparison=Path(paths['out'])/'pilot_comparison.json'
            from .base import load_json
            if load_json(comparison,{}).get('status')!='PASS':
                raise RuntimeError('Four-region independent GEE Gate-C benchmark not passed; do NOT run global')
        print(json.dumps(run_blocks(frozen_grid(args.root),paths['index'],args.root,
           paths['out'],workers=args.workers,block=10,
           full=cmd=='wc-full',pilot_blocks=4 if cmd=='wc-pilot' else 0),indent=2))
    elif cmd=='wc-compare':
        paths=default_paths(args.root)
        ref=args.reference_dir or str(Path(args.root)/'gate_c_reference')
        print(json.dumps(compare_gate_c(paths['out'],ref,Path(paths['out'])/'pilot_comparison.json'),indent=2))
    elif cmd=='wc-verify':
        paths=default_paths(args.root)
        print(json.dumps(verify_global(paths['out'],frozen_grid(args.root),require_full=not args.partial),indent=2))
    elif cmd=='gee-probe':print(json.dumps(source_probe(),indent=2))
    elif cmd=='merit-plan':print(json.dumps(merit_plan(args.block),indent=2))
    elif cmd=='merit-pilot':print(json.dumps(merit_submit(pilot=True,execute=args.execute,confirm=args.confirm),indent=2))
    elif cmd=='merit-next':
        plan=Path(__file__).resolve().parents[1]/'plans'/f'merit_{args.block}_all.csv'
        print(json.dumps(merit_submit(plan=plan,execute=args.execute,confirm=args.confirm),indent=2))
    elif cmd=='merit-audit':print(json.dumps(merit_audit(args.key,args.file),indent=2))
    elif cmd=='merit-merge':print(json.dumps(merit_merge(),indent=2))
    elif cmd=='weather-plan':print(json.dumps(weather_plan(args.events,args.block),indent=2))
    elif cmd=='weather-pilot':print(json.dumps(weather_submit(pilot=True,date=args.date,execute=args.execute,confirm=args.confirm),indent=2))
    elif cmd=='weather-next':
        import pandas as pd
        from .gee_runner import EVENT_LEDGER
        from .base import load_json
        plan=Path(__file__).resolve().parents[1]/'plans'/'weather_tasks.csv'
        if not plan.is_file():raise FileNotFoundError('Run weather-plan after freezing GF10-grid-day sample')
        done={z['key'] for z in load_json(EVENT_LEDGER,[])}
        df=pd.read_csv(plan)
        remaining=df.loc[~df.key.isin(done)]
        if remaining.empty:print(json.dumps({'status':'EVENT_TASK_PLAN_SUBMITTED'}));return
        print(json.dumps(weather_submit(key=str(remaining.iloc[0]['key']),execute=args.execute,confirm=args.confirm),indent=2))
    elif cmd=='weather-audit':print(json.dumps(weather_audit(args.key,args.file),indent=2))
    elif cmd=='gee-status':print(json.dumps(all_status(),indent=2))
    else:raise RuntimeError(cmd)

if __name__=='__main__':main()
