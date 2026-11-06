"""Do not fabricate scientific equivalence at EPSG:6933 anti-meridian domain."""
from __future__ import annotations
import pathlib,re
import pandas as pd
from . import core

def plan(root,pkg):
 f=core.root_files(root);q=pd.read_csv(f['v4']/'plans'/'merit_quarantine_v4.csv')
 if len(q)!=14:raise ValueError('Wrong seam quarantine record count')
 g=core.validate_grid(f['grid'])
 # Tile coordinates are read from the original frozen V4 manifest, never invented.
 ids=[]
 for z in q.itertuples(index=False):
  n=0
  # Explicit gf10 indexes per source parent (not accepted MERIT core):
  key=str(z.tile_key)
  m=re.fullmatch(r'merit_(-?\d+)_(-?\d+)_10',key)
  if not m:raise ValueError('Unexpected frozen seam parent tile key '+key)
  x=int(m.group(1));y=int(m.group(2))
  a=g[g.grid_x.between(x,x+9)&g.grid_y.between(y,y+9)].copy()
  n=len(a)
  a['seam_parent']=str(z.tile_key)
  ids.append(a)
 s=pd.concat(ids,ignore_index=True)
 if len(s)!=450 or s.grid_id.duplicated().any():raise ValueError(f'Seam land conservation mismatch: {len(s)} != 450')
 out=pathlib.Path(pkg)/'plans'/'seam450_GF10_geography_and_method_diagnostic.csv'
 if out.exists():raise FileExistsError('Source seam audit already exists')
 s.to_csv(out,index=False)
 return {'status':'SEAM_450_EXPLICITLY_QUARANTINED_UNTIL_INDEPENDENT_EE_SOURCE_PROBE','n_cells':450,
   'n_parents':14,'diagnostic_sha256':core.sha(out),
   'required_science':'Test each real partial GF10 grid location under split antimeridian geometry against native MERIT reference, source support and 16-band semantics; do not label as completed merely because an image exported'}
