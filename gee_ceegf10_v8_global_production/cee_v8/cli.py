"""Self-contained Windows production entrypoint (cloud commands explicit)."""
from __future__ import annotations
import argparse,pathlib,json
from . import core,plan,runner,assemble,seam

def main(argv=None):
 p=argparse.ArgumentParser('CEE GF10 V8 reproducible MERIT and IMERG/ERA5 global extraction')
 p.add_argument('--root',default=r'E:\GEE_flooding')
 p.add_argument('--pkg',default=r'E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106')
 sub=p.add_subparsers(dest='cmd',required=True)
 a=sub.add_parser('prepare');a.add_argument('--no-date-sensitivity',action='store_true');a.add_argument('--max-rows',type=int,default=260);a.add_argument('--max-days',type=int,default=4);a.add_argument('--geo-span-cells',type=int,default=0)
 sub.add_parser('register');sub.add_parser('status');sub.add_parser('seam-diagnostic')
 for x in ['tick','run']:
  a=sub.add_parser(x);a.add_argument('--execute',action='store_true');a.add_argument('--confirm')
  a.add_argument('--storage',choices=['gcs','drive'],default='drive');a.add_argument('--bucket')
  a.add_argument('--month-used-eecu',type=float);a.add_argument('--budget-limit-eecu',type=float,default=900)
  a.add_argument('--max-inflight',type=int,default=5);a.add_argument('--max-unaccepted',type=int,default=20)
  a.add_argument('--poll-seconds',type=int,default=90)
 for x in ['assemble-weather','assemble-merit']:
  a=sub.add_parser(x);a.add_argument('--allow-partial',action='store_true')
 args=p.parse_args(argv)
 root=pathlib.Path(args.root);pkg=pathlib.Path(args.pkg)
 if args.cmd=='prepare':
  res=plan.build_reuse_plan(root,pkg/'plans',not args.no_date_sensitivity,args.max_rows,args.max_days,args.geo_span_cells)
 elif args.cmd=='register':res=runner.register(root,pkg)
 elif args.cmd=='status':res=runner.one_tick(root,pkg,'drive',None,execute=False)
 elif args.cmd=='seam-diagnostic':res=seam.plan(root,pkg)
 elif args.cmd=='assemble-weather':res=assemble.weather(root,pkg,allow_partial=args.allow_partial)
 elif args.cmd=='assemble-merit':res=assemble.merit(root,pkg,allow_partial=args.allow_partial)
 else:
  if args.execute and args.confirm!=core.RUN:raise ValueError('Exact --confirm '+core.RUN+' required; never silently submit global tasks')
  if args.execute and args.month_used_eecu is None:raise ValueError('Obtain current project-wide monthly EECU from Cloud Monitoring; --month-used-eecu required')
  if args.cmd=='tick':
   res=runner.one_tick(root,pkg,args.storage,args.bucket,args.max_inflight,args.max_unaccepted,args.month_used_eecu,args.budget_limit_eecu,execute=args.execute)
  else:
   if not args.execute:raise ValueError('run is a live controller; require --execute and immutable --confirm')
   res=runner.run_loop(root,pkg,args.storage,args.bucket,args.max_inflight,args.max_unaccepted,args.month_used_eecu,args.budget_limit_eecu,args.poll_seconds)
 print(json.dumps(res,ensure_ascii=False,indent=2,default=str))
 return res
if __name__=='__main__':main()
