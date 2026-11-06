"""Windows-safe explicit CLI, no cloud submit except --execute + exact run-id."""
from __future__ import annotations
import argparse,json,pathlib,sys
from . import core,builder,review,candidates,gee

ROOT=pathlib.Path(r'E:\GEE_flooding')

def sources(root):
    root=pathlib.Path(root)
    return {'raw':root/'data'/'raw'/'groundsource_2026.parquet',
            'tiers':root/'outputs'/'fig1_publication_r3'/'labels'/'raw_uuid_tiers.parquet',
            'grid':root/'gee_ceegf10_v1'/'gf10_global_nonantarctic_land.parquet',
            'v6':root/'CEE_GF10_V6_SCIENCE_COHORT_20261105',
            'v3':root/'CEE_GF10_EFFICIENT_V3_20261105',
            'v4':root/'CEE_GF10_GEE_RECOVERY_V4_20261105'}

def locate_ucdb(root,explicit=None):
    if explicit:
        p=pathlib.Path(explicit)
        if not p.is_file():raise FileNotFoundError(p)
        return p
    root=pathlib.Path(root)
    attempts=[root/'data'/'reference'/'GHS_UCDB_GLOBE_R2024A.gpkg',
              root/'data'/'raw'/'ucdb'/'GHS_UCDB_GLOBE_R2024A.gpkg',
              pathlib.Path(r'E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg')]
    found=[x for x in attempts if x.exists()]
    if len(found)!=1:raise ValueError('Exactly one official GHS-UCDB R2024A source required. Located '+str(found)+'; use --ucdb')
    return found[0]

def inspect(args):
    from pyarrow import parquet as pq
    s=sources(args.root);o={'status':'SOURCE_INVENTORY_NO_GEE','project':core.PROJECT}
    for key in ('raw','tiers','grid'):
        f=s[key]
        if not f.is_file():raise FileNotFoundError(f)
        p=pq.ParquetFile(f)
        o[key]={'path':str(f),'sha256':core.digest(f),'rows':p.metadata.num_rows,'columns':p.schema_arrow.names}
    city=locate_ucdb(args.root,args.ucdb)
    o['ucdb']={'path':str(city),'sha256':core.digest(city),'classification':'official city polygons; not flood footprints'}
    o['gf10_expected_sha256']=core.GF10_HASH
    o['source_schema_sufficient_to_verify_articles_independently']=False
    o['source_only_temporal_grade']='SINGLE_DAY_SOURCE_CLAIM_NOT_VERIFIED_UTC_INSTANT'
    target=pathlib.Path(args.out)/'reports'/'source_inventory_v7.json'
    core.write_json(target,o,replace=args.force)
    return o

def merit_status(args):
    import pandas as pd
    root=pathlib.Path(args.root);s=sources(root)
    gate=core.read_json(s['v6']/'reports'/'merit_halo_science_gate_v6.json')
    if not gate or gate.get('status')!='PASS_20_40_80_HALO_NUMERIC_CONVERGENCE':
        raise ValueError('MERIT v6 three-stratum numerical gate not passed')
    p=s['v4']/'plans'/'merit_safe_v4.csv'
    plan=pd.read_csv(p)
    t=core.read_json(s['v6']/'reports'/'v6_tasks.json',[])
    done={str(z['base_tile_key']) for z in t if z.get('kind')=='MERIT_FINAL80_SINGLE_TILE' and z.get('local_qc_pass')}
    done|={str(z['base_tile_key']) for z in t if z.get('kind')=='MERIT_BUFFER_CONVERGENCE' and z.get('halo_km')==80 and z.get('local_qc_pass')}
    # Prior v4 geometry-only tasks are not assumed 80km science-equivalent.
    remain=plan.loc[~plan.tile_key.isin(done)]
    keys=remain.tile_key.head(args.n).tolist()
    return {'status':'MERIT_HALO_CONVERGENCE_PASS_GLOBAL_INCOMPLETE','n_safe_plan':len(plan),
      'n_accepted_80km_tile_keys':len(done),'n_safe_remaining':len(remain),
      'seam_quarantine_not_counted_as_complete':14,'seam_cells':450,
      'next_unsubmitted_keys':keys,'execute_with_prior_validated_v6_cli':[
        f'python -m cee_v6 merit-submit --root "{root}" --key "{k}" --execute --confirm CEE_GF10_MERIT_M0_SCIENCE_V6_20261105'
        for k in keys],
      'caution':'Do not repeat existing verified 80km tiles; each live export needs download+QC+EECU+SHA.'}

def main(argv=None):
    p=argparse.ArgumentParser(description='CEE Figure1 UUID provenance and bounded GEE date extraction v7')
    p.add_argument('--root',default=str(ROOT));p.add_argument('--out',default=None)
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('inspect');a.add_argument('--ucdb');a.add_argument('--force',action='store_true')
    a=sub.add_parser('build-source');a.add_argument('--ucdb');a.add_argument('--city-field');a.add_argument('--city-layer')
    a.add_argument('--start',default='2021-01-01');a.add_argument('--end',default='2023-12-31')
    a.add_argument('--max-area-km2',type=float,default=25.);a.add_argument('--batch',type=int,default=30000)
    a.add_argument('--test-grid',action='store_true',help='Synthetic unit tests only; never for publication')
    a.add_argument('--allow-changed-raw-sha',action='store_true')
    a=sub.add_parser('cases');a.add_argument('--review-n',type=int,default=400)
    a=sub.add_parser('verify-manual');a.add_argument('--review-file',required=True)
    a=sub.add_parser('cohort-plan');a.add_argument('--per-case',type=int,default=4)
    a.add_argument('--max-cells',type=int,default=40);a.add_argument('--verified-only',action='store_true')
    a=sub.add_parser('weather-preflight')
    a=sub.add_parser('weather-submit');a.add_argument('--key',required=True)
    a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
    a.add_argument('--pilot-limit',type=int,default=3);a.add_argument('--budget-eecu',type=float,default=0.5)
    a=sub.add_parser('weather-status')
    a=sub.add_parser('weather-audit');a.add_argument('--key',required=True);a.add_argument('--file',required=True)
    a.add_argument('--require-fully-valid',action='store_true')
    a=sub.add_parser('weather-assemble')
    a=sub.add_parser('weather-match');a.add_argument('--policy',required=True)
    a.add_argument('--publication',action='store_true');a.add_argument('--rain-p95')
    a.add_argument('--storm-catalog');a.add_argument('--verified-only',action='store_true')
    a=sub.add_parser('merit-next');a.add_argument('--n',type=int,default=6)
    args=p.parse_args(argv)
    root=pathlib.Path(args.root);work=pathlib.Path(args.out or root/core.NAME);s=sources(root)
    if args.cmd=='inspect':res=inspect(args)
    elif args.cmd=='build-source':
        if args.test_grid:raise ValueError('Test grid cannot be used for production source matching')
        res=builder.extract(s['raw'],s['tiers'],s['grid'],locate_ucdb(root,args.ucdb),
            work/'data'/'source_lineage',args.city_field,args.city_layer,
            start=args.start,end=args.end,max_area_km2=args.max_area_km2,batch_size=args.batch,
            strict_raw_sha=None if args.allow_changed_raw_sha else '77c266ba5a5176d983edca989a81ff73f21c556fd98c82e2131c2f8d172546ce')
    elif args.cmd=='cases':res=review.create_cases(work/'data'/'source_lineage'/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet',
          work/'data'/'case_source',review_n=args.review_n)
    elif args.cmd=='verify-manual':res=review.manual_verify(
       work/'data'/'source_lineage'/'groundsource_uuid_to_gf10_ucdb_PROVISIONAL.parquet',
       args.review_file,work/'data'/'case_verified')
    elif args.cmd=='cohort-plan':
        case=work/'data'/('case_verified' if args.verified_only else 'case_source')/(
           'reported_grid_day_cases_MANUALLY_VERIFIED.parquet' if args.verified_only else 'reported_source_day_cases_PROVISIONAL.parquet')
        res=candidates.write_cohort(case,s['grid'],work/'plans',n=args.per_case,max_cells=args.max_cells)
    elif args.cmd=='weather-preflight':res=gee.preflight(work,s['grid'],s['v6'])
    elif args.cmd=='weather-submit':res=gee.submit(work,s['grid'],s['v6'],s['v3'],args.key,
           execute=args.execute,confirm=args.confirm,pilot_limit=args.pilot_limit,max_eecu_h=args.budget_eecu)
    elif args.cmd=='weather-status':res=gee.status(work)
    elif args.cmd=='weather-audit':res=gee.audit(work,args.key,args.file,strict_valid_rows=args.require_fully_valid)
    elif args.cmd=='weather-assemble':res=gee.assemble(work,work/'data'/'weather_live_qc_accepted_PARTIAL.parquet')
    elif args.cmd=='weather-match':
        if args.publication and not args.verified_only:
            raise ValueError('Publication mode requires --verified-only and real manual case evidence')
        if args.publication and (not args.rain_p95 or not args.storm_catalog):
            raise ValueError('Publication mode requires independent daily P95 and verified storm catalogue')
        import sys
        sys.path.insert(0,str(s['v6']))
        from cee_v6 import matching
        from pandas import read_parquet
        candidates_file=work/'plans'/'reported_and_UNLABELED_calendar_candidates.parquet'
        weather=work/'data'/'weather_live_qc_accepted_PARTIAL.parquet'
        cohort=read_parquet(candidates_file)
        if args.verified_only:
            verified=read_parquet(work/'data'/'case_verified'/'reported_grid_day_cases_MANUALLY_VERIFIED.parquet')
            cohort=cohort[cohort.case_id.isin(verified.case_id)].copy()
            if cohort.empty:raise ValueError('No matching independent manual cases')
        merged=matching.attach_weather(cohort,read_parquet(weather))
        climate=read_parquet(args.rain_p95) if args.rain_p95 else None
        storm=read_parquet(args.storm_catalog) if args.storm_catalog else None
        matched,qc=matching.weather_match(merged,core.read_json(args.policy),
            storm_mapping=storm,require_independent_storm=args.publication,
            climate_thresholds=climate,publication=args.publication)
        dest=work/'data'/('weather_matched_PUBLICATION_CANDIDATE.parquet' if args.publication
                           else 'weather_matched_EXPLORATORY_ONLY.parquet')
        core.ensure_new(dest);matched.to_parquet(dest,index=False)
        res={**qc,'output':str(dest),'not_true_flood_negatives':True,
             'source_day_UTC_proxy':True,'requires_local_day_UTC_uncertainty_robustness':True}
        core.write_json(dest.with_suffix('.qc.json'),res)
    elif args.cmd=='merit-next':res=merit_status(args)
    else:raise RuntimeError('Unknown command')
    print(json.dumps(res,indent=2,ensure_ascii=False,default=str))
    return res

if __name__=='__main__':main()
