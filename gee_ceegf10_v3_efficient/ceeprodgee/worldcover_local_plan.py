"""Deterministic study-independent GF10 global/study/pilot plans for local ESA COGs."""
from __future__ import annotations
import argparse,json,pathlib
from . import grid,contract
FOUR={'wuhan':(1097,367),'mumbai':(697,233),
      'iceland':(-166,658),'niger_delta':(57,52)}

def make(args):
    import pandas as pd
    base=grid.read_grid(args.grid,strict=True)
    if args.scope=='pilot-four':
        # Gate C 4 x 10x10 = sixteen 5x5 source blocks.
        tiles=[]
        for name,(x0,y0) in FOUR.items():
            for a in (0,5):
                for b in (0,5):
                    x,y=x0+a,y0+b
                    cell=base[base.grid_x.between(x,x+4)&base.grid_y.between(y,y+4)]
                    tiles.append({'family':'worldcover','tile_key':f'worldcover_{x}_{y}_5',
                                  'tile_x0':x,'tile_y0':y,'tile_size':5,
                                  'n_land_cells':len(cell),'n_work_pixels':25,
                                  'gate_c_region':name})
        out=pd.DataFrame(tiles)
    else:
        selected=None
        if args.scope=='study':
            if not args.study_ids:raise ValueError('Study mode requires pre-frozen 2020 urban GF10 IDs')
            path=pathlib.Path(args.study_ids)
            if not path.exists():raise FileNotFoundError(path)
            df=pd.read_parquet(path,columns=['grid_id']) if path.suffix=='.parquet' else pd.read_csv(path,usecols=['grid_id'])
            selected=df.grid_id.astype(str).tolist()
        out=grid.make_plan(base,'worldcover',selected)
    p=pathlib.Path(args.out);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        old=pd.read_csv(p)
        if not old.equals(out):raise FileExistsError('Frozen study scope changed; refuse overwrite: '+str(p))
    else:out.to_csv(p,index=False)
    s={'status':'PLAN_ONLY_NO_GEE','scope':args.scope,'n_tiles':len(out),
       'n_export_pixels':int(out.n_work_pixels.sum()),'n_registered_land_cells':int(out.n_land_cells.sum()),
       'source':'ESA official WorldCover 2021 v200 3deg COGs',
       'method':'local 10m equal-area nearest categorical warp, GSHHG native 10m land-mask, 5x5 tiles',
       'note':'No flood-report labels used in selection; pilot-four tiles are explicit Gate C locations'}
    p.with_suffix('.plan.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
    print(json.dumps(s,ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--grid',required=True);p.add_argument('--out',required=True)
    p.add_argument('--scope',choices=['pilot-four','study','all'],default='pilot-four')
    p.add_argument('--study-ids')
    make(p.parse_args())
if __name__=='__main__':main()
