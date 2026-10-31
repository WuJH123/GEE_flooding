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
    commands.add_parser('inventory',help='Check already available E-drive datasets; NO DOWNLOAD')
    s=commands.add_parser('summarize-labels',help='Unique news UUID/grid-day and annual quality summary; NO DOWNLOAD')
    s.add_argument('--labels',type=Path,default=None)
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
    s=commands.add_parser('fig1',help='GEE article Figure1: news coverage, city eligibility, source concordance; NO DOWNLOAD')
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--labels',type=Path,required=True)
    s.add_argument('--label-qc',type=Path,required=True)
    s.add_argument('--ucdb',type=Path,required=True)
    s.add_argument('--ucdb-crosswalk',type=Path)
    s.add_argument('--koppen',type=Path)
    s.add_argument('--gfid',type=Path)
    s.add_argument('--world',type=Path)
    s.add_argument('--physical',type=Path)
    s.add_argument('--tag',default='fig1_v1')
    s.add_argument('--city-min-reports',type=int,default=5)
    s.add_argument('--city-min-years',type=int,default=3)
    s=commands.add_parser('fig1-v3',help='P0 audit + publication draft figure, NO downloads or GEE submissions')
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--labels',type=Path,required=True)
    s.add_argument('--label-qc',type=Path,required=True)
    s.add_argument('--v2-dir',type=Path,required=True)
    s.add_argument('--gfid',type=Path,required=True)
    s.add_argument('--gfid-duplicates',type=Path)
    s.add_argument('--world',type=Path)
    s.add_argument('--physical',type=Path,help='independently reviewed observational positives CSV')
    s.add_argument('--reviewer-table',type=Path,help='completed manual news annotation CSV')
    s.add_argument('--review-n',type=int,default=600)
    s.add_argument('--tag',default='fig1_v3')
    s.add_argument('--fast',action='store_true',help='1k grid-day GFID matching SMOKE ONLY; never publish')
    s=commands.add_parser('fig1-review-audit',help='Human adjudication and incomplete-review gate')
    s.add_argument('--queue',type=Path,required=True)
    s.add_argument('--reviews',type=Path,required=True)
    s.add_argument('--tag',default='fig1_review_r1')
    s=commands.add_parser('fig1-gfd-probe',help='One known GFD event and one original GF10 cell; dry-run by default')
    s.add_argument('--project',required=True)
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--grid-id',required=True)
    s.add_argument('--gfd-event-id',type=int,required=True)
    s.add_argument('--description',default='FIG1_GFD_VERIFIED_WATER_PILOT')
    s.add_argument('--submit',action='store_true')
    s=commands.add_parser('fig1-preflight',help='P0 metadata and source-ledger validation, no downloads')
    s.add_argument('--raw',type=Path,required=True)
    s.add_argument('--mapped',type=Path,required=True)
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--city-file',type=Path,required=True)
    s.add_argument('--v3-qc',type=Path,required=True)
    s.add_argument('--crosswalk',type=Path,required=True)
    s.add_argument('--tag',default='fig1_preflight_r1')
    s=commands.add_parser('fig1-prepare-weather-pilot',help='Stratified 24-observation manifest for IMERG/ERA5, no submission')
    s.add_argument('--tiers',type=Path,required=True)
    s.add_argument('--grid',type=Path,required=True)
    s.add_argument('--tag',default='fig1_pilot_r1')
    s.add_argument('--n',type=int,default=24)
    s.add_argument('--seed',type=int,default=42)
    s.add_argument('--paired-controls',action='store_true',
                   help='same-grid season nearby no-news dates are UNLABELED, not dry negatives')
    s=commands.add_parser('fig1-gee-pilot',help='Dry-run by default; optional bounded 12-row EE table export')
    s.add_argument('--project',required=True)
    s.add_argument('--manifest',type=Path,required=True)
    s.add_argument('--description',default='FIG1_IMERG_V07_PILOT')
    s.add_argument('--max-rows',type=int,default=12)
    s.add_argument('--submit',action='store_true')
    s=commands.add_parser('fig1-ucdb-population',help='Inspect official UCDB fields or export explicitly verified 2020 population')
    s.add_argument('--ucdb',type=Path,required=True)
    s.add_argument('--layer',default='GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A')
    s.add_argument('--population-field',default=None)
    s.add_argument('--tag',default='fig1_publication_v1')
    s=commands.add_parser('fig1-spatial-frame',help='Frozen GF10 core + verified adjacent raster periphery, NO DOWNLOAD')
    s.add_argument('--core',type=Path,required=True)
    s.add_argument('--west',type=Path,required=True)
    s.add_argument('--east',type=Path,required=True)
    s.add_argument('--tag',default='fig1_publication_v1')
    s=commands.add_parser('fig1-tier-audit',help='Raw Groundsource UUID -> A/B/C proxy tiers and candidate observation units')
    s.add_argument('--raw',type=Path,required=True)
    s.add_argument('--primary',type=Path,required=True)
    s.add_argument('--tag',default='fig1_publication_v1')
    s=commands.add_parser('fig1-paper',help='Five-panel paper draft: requires audited frozen inputs and honest evidence gate')
    s.add_argument('--tag',default='fig1_publication_v1')
    s.add_argument('--spatial-dir',type=Path,required=True)
    s.add_argument('--tier-dir',type=Path,required=True)
    s.add_argument('--city-file',type=Path,required=True)
    s.add_argument('--crosswalk',type=Path,required=True)
    s.add_argument('--v3-qc',type=Path,required=True)
    s.add_argument('--physical-reviewed',type=Path)
    s.add_argument('--city-population',type=Path)
    s.add_argument('--independent-storm-manifest',type=Path)
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
    if args.command=='inventory':
        from .audit import inventory
        print(inventory(root));return
    if args.command=='summarize-labels':
        from .audit import summarize_labels
        print(summarize_labels(root,args.labels));return
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
    elif args.command=='fig1-v3':
        from .fig1_v3 import build
        result=build(root,args.labels,args.grid,args.label_qc,args.v2_dir,
                     args.gfid,duplicates=args.gfid_duplicates,
                     physical=args.physical,tag=args.tag,
                     world=args.world,reviewer_table=args.reviewer_table,
                     review_n=args.review_n,fast=args.fast)
    elif args.command=='fig1-review-audit':
        from .fig1_review import summarize
        result=summarize(root,args.queue,args.reviews,args.tag)
    elif args.command=='fig1-gfd-probe':
        from .fig1_gfd_probe import gfd_probe
        result=gfd_probe(args.project,args.grid,args.grid_id,args.gfd_event_id,
                         args.submit,args.description)
    elif args.command=='fig1-preflight':
        from .fig1_preflight import inspect
        result=inspect(root,args.raw,args.mapped,args.grid,args.city_file,
                       args.v3_qc,args.crosswalk,args.tag)
    elif args.command=='fig1-prepare-weather-pilot':
        from .fig1_gee_pilot import prepare
        result=prepare(root,args.tiers,args.grid,args.tag,args.n,args.seed,
                       paired_controls=args.paired_controls)
    elif args.command=='fig1-gee-pilot':
        from .fig1_gee_pilot import run_gee
        result=run_gee(args.project,args.manifest,args.description,
                       args.submit,args.max_rows)
    elif args.command=='fig1-ucdb-population':
        from .fig1_ucdb_population import inspect
        result=inspect(root,args.ucdb,args.layer,args.population_field,args.tag)
    elif args.command=='fig1-spatial-frame':
        from .fig1_spatial import freeze_periphery
        result=freeze_periphery(root,args.core,args.west,args.east,args.tag)
    elif args.command=='fig1-tier-audit':
        from .fig1_tiers import build_labels_release
        result=build_labels_release(root,args.raw,args.primary,args.tag)
    elif args.command=='fig1-paper':
        from .fig1_publication import run
        result=run(root,args.tag,args.spatial_dir,args.tier_dir,
                   args.city_file,args.crosswalk,args.v3_qc,
                   physical_file=args.physical_reviewed,
                   city_population=args.city_population,storms=args.independent_storm_manifest)
    elif args.command=='fig1':
        from .fig1 import build
        result=build(root,args.grid,args.labels,args.label_qc,args.ucdb,
                     tag=args.tag,crosswalk=args.ucdb_crosswalk,
                     koppen=args.koppen,gfid=args.gfid,world=args.world,
                     physical=args.physical,city_min_reports=args.city_min_reports,
                     city_min_years=args.city_min_years)
    print(result)

if __name__=='__main__':main()
