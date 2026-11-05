from __future__ import annotations
import argparse,pathlib,json
from . import cohort,common,production,matching,science,assemble
R=common.ROOT

def pth(x):return str(pathlib.Path(x).resolve())

def main(argv=None):
    p=argparse.ArgumentParser(description='CEE v6 science-gated MERIT and audited two-stage IMERG/ERA5-Land event workflow')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('inspect-fig1');a.add_argument('--source',required=True);a.add_argument('--report')
    a=sub.add_parser('freeze-cases');a.add_argument('--source',required=True);a.add_argument('--mapping',required=True)
    a.add_argument('--grid',required=True);a.add_argument('--out',default=str(R/'data'/'cohort_v6'))
    a.add_argument('--start',default='2021-01-01');a.add_argument('--end',default='2023-12-31')
    a=sub.add_parser('calendar-candidates');a.add_argument('--cases',required=True);a.add_argument('--out',default=str(R/'data'/'cohort_v6'))
    a.add_argument('--per-case',type=int,default=8)
    a=sub.add_parser('weather-request-plan');a.add_argument('--cohort',required=True);a.add_argument('--grid',required=True)
    a.add_argument('--strict-grid',action='store_true',default=True)
    a=sub.add_parser('halo-submit');a.add_argument('--root',required=True);a.add_argument('--key',required=True)
    a.add_argument('--halo',type=int,choices=[20,40,80],required=True);a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('merit-submit');a.add_argument('--root',required=True);a.add_argument('--key',required=True)
    a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a.add_argument('--recalibrate-legacy',action='store_true');a.add_argument('--reason')
    a=sub.add_parser('halo-audit');a.add_argument('--key',required=True);a.add_argument('--file',required=True)
    a=sub.add_parser('halo-compare');a.add_argument('--tile-key',required=True)
    a.add_argument('--tif20',required=True);a.add_argument('--tif40',required=True);a.add_argument('--tif80',required=True)
    a.add_argument('--root',required=True)
    a=sub.add_parser('halo-approve');a.add_argument('--report-dir',default=str(R/'reports'))
    a=sub.add_parser('weather-submit');a.add_argument('--root',required=True);a.add_argument('--key',required=True)
    a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a=sub.add_parser('weather-audit');a.add_argument('--root',required=True);a.add_argument('--key',required=True);a.add_argument('--file',required=True)
    a=sub.add_parser('live-accept');a.add_argument('--root',required=True);a.add_argument('--key',required=True)
    a=sub.add_parser('status');a.add_argument('--root',required=True)
    a=sub.add_parser('weather-assemble');a.add_argument('--downloads',default=str(R/'downloads'))
    a.add_argument('--out',default=str(R/'data'/'cohort_v6'/'weather_verified_v6.parquet'))
    a.add_argument('--allow-partial',action='store_true')
    a=sub.add_parser('merit-assemble');a.add_argument('--root',required=True)
    a.add_argument('--out',default=str(R/'data'/'merit_v6_science_accepted_partial.parquet'))
    a=sub.add_parser('weather-match');a.add_argument('--cohort',required=True);a.add_argument('--weather',required=True)
    a.add_argument('--policy',required=True);a.add_argument('--storm-map');a.add_argument('--require-storms',action='store_true')
    a.add_argument('--rain-p95');a.add_argument('--publication',action='store_true')
    a.add_argument('--out',default=str(R/'data'/'cohort_v6'/'weather_matched_provisional.parquet'))
    args=p.parse_args(argv)
    if args.cmd=='inspect-fig1':
        z=cohort.inspect(args.source)
        if args.report:common.save(args.report,z)
    elif args.cmd=='freeze-cases':
        mapping=common.load(args.mapping)
        _,z=cohort.freeze_cases(args.source,mapping,args.grid,args.out,start=args.start,end=args.end)
    elif args.cmd=='calendar-candidates':
        cases=common.readtab(args.cases)
        rows,z=cohort.generate_calendar_candidates(cases,args.per_case)
        common.writetab(rows,pathlib.Path(args.out)/'preweather_reported_and_unlabeled_candidates.parquet')
        common.save(pathlib.Path(args.out)/'candidate_qc.json',z)
    elif args.cmd=='weather-request-plan':
        d,plan=cohort.make_request_plan(common.readtab(args.cohort),common.check_grid(args.grid))
        common.writetab(d,R/'plans'/'event_grid_days_v6.parquet')
        path=R/'plans'/'event_requests_v6.csv';path.parent.mkdir(exist_ok=True,parents=True)
        if path.exists():raise FileExistsError('Immutable weather plan exists: '+str(path))
        plan.to_csv(path,index=False)
        z={'status':'WEATHER_CANDIDATE_REQUESTS_ONLY','n_grid_days':len(d),
           'n_date_tile_tasks':len(plan),'n_dates':int(d.date_utc.nunique()),
           'storm_verified':False,'ready_for_case_control_M0_exposure_pilot':True,
           'source_sha256':common.sha(args.cohort),'grid_sha256':common.sha(args.grid)}
        common.save(R/'plans'/'event_requests_v6.qc.json',z)
    elif args.cmd=='halo-submit':
        z=production.static_halo_submit(args.root,args.key,args.halo,args.execute,args.confirm)
    elif args.cmd=='merit-submit':
        z=production.static_production_submit(args.root,args.key,args.execute,args.confirm,args.recalibrate_legacy,args.reason)
    elif args.cmd=='halo-audit':
        z=production.audit_halo(args.key,args.file)
    elif args.cmd=='halo-compare':
        _,bbox=production.safe_record(production.old_context(args.root)[-1],args.root,args.tile_key)
        x0,y0,x1,y1=bbox
        crop={'width':int((x1-x0)//10000),'height':int((y1-y0)//10000)}
        rows=[]
        for a,b,f,g in [(20,40,args.tif20,args.tif40),(40,80,args.tif40,args.tif80)]:
            stats=science.compare_rasters(f,g,crop)
            rows.append({'tile_key':args.tile_key,'ref_halo_km':a,'probe_halo_km':b,
             'source_tif_sha256':common.sha(g),'reference_tif_sha256':common.sha(f),'bands':stats})
        path=R/'reports'/('halo_'+args.tile_key+'.json')
        common.save(path,{'comparisons':rows,'status':'MEASURED_NOT_APPROVED'})
        z={'output':str(path),'n_bands':16,'n_pairs':2}
    elif args.cmd=='halo-approve':
        # A synthetic or copied comparator JSON is NOT enough: every source
        # GeoTIFF must be in a completed, QC-accepted v6 ledger entry.
        registry=common.load(production.CLOUD) if production.CLOUD.exists() else []
        validated={z['key']:z for z in registry if z.get('local_qc_pass') is True and
                   z.get('local_file_sha256') and z.get('kind')=='MERIT_BUFFER_CONVERGENCE'}
        rows=[]
        keys=['merit_1090_360_10','merit_700_230_10','merit_-1720_670_10']
        for key in keys:
            for n in (20,40,80):
                candidate='halo'+str(n)+'_'+key
                if candidate not in validated:
                    raise ValueError('Missing live verified GEE + TIFF QC for '+candidate)
            f=pathlib.Path(args.report_dir)/('halo_'+key+'.json')
            if not f.is_file():raise FileNotFoundError('3 climates needed for approval: '+str(f))
            comparisons=common.load(f)['comparisons']
            for item in comparisons:
                left=validated['halo'+str(item['ref_halo_km'])+'_'+key]
                right=validated['halo'+str(item['probe_halo_km'])+'_'+key]
                if item['source_tif_sha256']!=right['local_file_sha256'] or item['reference_tif_sha256']!=left['local_file_sha256']:
                    raise ValueError('Halo comparison uses a TIFF absent from the verified GEE task ledger')
            rows.extend(comparisons)
        z=science.approve(rows,keys,R/'reports'/'merit_halo_science_gate_v6.json')
    elif args.cmd=='weather-submit':
        z=production.request_submit(args.root,args.key,args.execute,args.confirm)
    elif args.cmd=='weather-audit':
        z=production.audit_weather(args.root,args.key,args.file)
    elif args.cmd=='live-accept':
        z=production.live_accept(args.root,args.key)
    elif args.cmd=='status':
        z=production.inspect_task_status(args.root)
    elif args.cmd=='weather-assemble':
        z=assemble.merge_verified_weather(args.downloads,args.out,args.allow_partial)
    elif args.cmd=='merit-assemble':
        z=assemble.merge_verified_merit(args.root,args.out)
    elif args.cmd=='weather-match':
        x=matching.attach_weather(common.readtab(args.cohort),common.readtab(args.weather))
        storm=common.readtab(args.storm_map) if args.storm_map else None
        thresholds=common.readtab(args.rain_p95) if args.rain_p95 else None
        y,z=matching.weather_match(x,common.load(args.policy),storm,args.require_storms,thresholds,args.publication)
        common.writetab(y,args.out)
        common.save(pathlib.Path(args.out).with_suffix('.qc.json'),z)
    else:raise RuntimeError('Unknown command')
    print(json.dumps(z,indent=2,ensure_ascii=False,default=str))

if __name__=='__main__':main()
