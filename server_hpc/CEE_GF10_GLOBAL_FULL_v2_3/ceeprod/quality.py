"""Scientifically meaningful full-region QC; no false 'publication_ready'."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
import numpy as np
from .shared import write_json,read_json


def scan_tile_group(path,expected_tiles=715,expected_rows=1_395_471):
    import pyarrow.parquet as pq
    root=Path(path);files=sorted((root/'tiles').glob('tile_*.parquet'))
    if len(files)!=expected_tiles:raise ValueError(f'Expected {expected_tiles} tiles, found {len(files)} under '+str(root))
    rows=0;duplicate=0;missing_qc=0;seen=set()
    for f in files:
        q=f.with_suffix('.qc.json')
        if not q.exists():missing_qc+=1;continue
        z=read_json(q)
        if z.get('status')!='OK':raise ValueError('Invalid tile QC '+str(q))
        meta=pq.ParquetFile(f).metadata
        if meta.num_rows!=z.get('rows',z.get('n_grid')):
            raise ValueError('Mismatch parquet metadata rows vs QC '+str(f))
        rows+=meta.num_rows
        ids=pd.read_parquet(f,columns=['grid_id']).grid_id
        duplicate+=int(ids.duplicated().sum())
        overlap=len(seen.intersection(ids.astype(str)))
        duplicate+=overlap
        if overlap:raise ValueError('Same GF10 ID written by multiple tiles '+str(f))
        seen.update(ids.astype(str))
    if missing_qc or rows!=expected_rows or duplicate:
        raise ValueError(f'QC conservation failed: rows={rows}/{expected_rows},missing_qc={missing_qc},duplicate={duplicate}')
    return {'status':'COMPLETE_ALL_FROZEN_GF10_ROWS','n_tiles':len(files),'n_grid':rows,
      'unique_grid_ids':len(seen)}


def summarize(root,strict=True):
    root=Path(root)
    groups={'gmted_mean':list((root/'data/derived/cee_all_v11/gmted').glob('*/run_qc.json')),
            'worldclim_bio':list((root/'data/derived/cee_all_v11/worldclim-bio').glob('*/run_qc.json')),
            'worldclim_monthly':list((root/'data/derived/cee_all_v11/worldclim-monthly').glob('*/run_qc.json')),
            'grip_density':list((root/'data/derived/cee_all_v11/grip-density').glob('*/run_qc.json')),
            'vector_global':list((root/'data/derived/cee_all_global_v2/vector').glob('*/run_qc.json'))}
    expected={'gmted_mean':5,'worldclim_bio':19,'worldclim_monthly':84,'grip_density':1,'vector_global':6}
    results={};errors=[]
    for family,files in groups.items():
        details=[]
        for qcfile in files:
            z=read_json(qcfile)
            counts=(int(z.get('n_tasks',z.get('n_tiles',0))),int(z.get('n_rows',z.get('n_grid',0))))
            if counts!=(715,1_395_471):
                errors.append(f'{family} {qcfile} has partial counts {counts}')
            details.append({'path':str(qcfile.parent),'status':z.get('status'),'counts':counts})
        if len(files)!=expected[family]:errors.append(f'{family}: found {len(files)} products, need {expected[family]}')
        results[family]=details
    for family in ('ghsl_built_2000','ghsl_built_2020','ghsl_nres_2020','ghsl_pop_2020','ghsl_smod_2020'):
        source=root/'data/derived'/f'hpc_exact_{family}_v2/run_qc.json'
        if not source.exists():errors.append('Missing frozen GHSL '+family);continue
        z=read_json(source)
        if z.get('n_tasks')!=715:errors.append('GHSL partial '+family)
        results[family]=z.get('status')
    for key,relative in {'era5ex':'era5ex_annual_wide','gisd30':'gisd30_history',
           'groundsource':'groundsource_reports'}.items():
        p=root/'data/derived/cee_all_global_v2'/relative/'run_qc.json'
        if not p.exists():errors.append('Missing '+key)
        else:results[key]=read_json(p)
    for fam in ('admin0','admin1','ucdb','basin','river','roads'):
        p=root/'data/derived/cee_all_global_v2/vector'/fam/'run_qc.json'
        if not p.exists():errors.append('Missing vector '+fam)
    for fam in ('ucdb','basin','admin0','admin1'):
        p=root/'data/derived/cee_all_global_v2/native_attributes'/fam/'run_qc.json'
        if not p.exists():errors.append('Missing native attributes '+fam)
    flood=root/'data/derived/cee_all_v11/flood_catalogue/qc.json'
    if not flood.exists():errors.append('Missing Global Flood Records catalogue')
    results['flood_catalogue']=read_json(flood) if flood.exists() else None
    # Stage-wide structural completeness != publication approval.
    results['structural_complete']=not bool(errors)
    results['publication_ready']=False
    results['remaining_science_gates']=['GSHHG land-only geometry for partial coast GF10',
      'GMTED elevation TIFF description says Maximum despite requested mean product',
      'worldclim temperature/scale native source metadata and era temporal leakage',
      'GISD30 30m global tile seam and class area weighting validation',
      'GRIP4/RiverATLAS length source coverage and antimeridian QA',
      'independent physical inundation labels and near-event meteorology']
    results['errors']=errors
    out=root/'reports/cee_global_v2_audit.json';write_json(out,results)
    if strict and errors:raise ValueError(f'Global production incomplete ({len(errors)} structural errors). See {out}: '+str(errors[:8]))
    return {'output':str(out),'structural_complete':not errors,'issues':len(errors),
        'publication_ready':False}
