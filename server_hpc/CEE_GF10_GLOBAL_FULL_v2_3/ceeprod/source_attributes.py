"""Preserve ALL official UCDB thematic fields and HydroATLAS/admin attributes.

UCDB is an urban-entity database, not a 10km source rasters. Each theme is
exported separately by its original stable provider ID; neither city-level
attributes nor projected/future epochs are fabricated as GF10 measurements.
"""
from __future__ import annotations
from pathlib import Path
import os,re
import pandas as pd
from .shared import prepare_directory,read_json,write_json,file_identity
from .discover import discover_family,discover_ucdb_themes


def _batches(src,batch_size):
    import pyogrio
    streamed=0
    try:
        with pyogrio.open_arrow(src.path,layer=src.layer,read_geometry=False,
                                use_pyarrow=True,batch_size=batch_size) as (_meta,reader):
            for block in reader:
                df=block.to_pandas()
                streamed+=len(df)
                yield df
        return
    except (TypeError,AttributeError,RuntimeError,NotImplementedError,ValueError) as exc:
        if streamed:
            raise RuntimeError(f'Native Arrow stream aborted after {streamed} provider rows, '
                               'no silent restart from row zero') from exc
        print(f'[attributes] Arrow stream unavailable for {src.family}/{src.layer}: {exc}; '
              'using bounded reads',flush=True)
    n=int(src.count)
    if n<0:raise ValueError('Unknown provider feature count; cannot use skip_features')
    for start in range(0,n,batch_size):
        result=pyogrio.read_dataframe(src.path,layer=src.layer,read_geometry=False,
             skip_features=start,max_features=min(n-start,batch_size),use_arrow=False)
        if result.empty:raise ValueError('Native provider attributes prematurely ended')
        yield result


def _export_one(outroot,src,family,batch_size=50000):
    import pyogrio,pyarrow.parquet as pq
    if not src.id_field:raise ValueError('Native provider lacks stable ID')
    out,jid=prepare_directory(outroot,{'source':file_identity(src.path),
         'layer':src.layer,'id':src.id_field,
         'algorithm':'original_native_attributes_arrow_stream_v22'})
    info=pyogrio.read_info(src.path,layer=src.layer)
    declared=int(info.get('features',-1))
    if declared<0:raise ValueError('Native provider feature count unavailable '+src.layer)
    offset=0;parts=[];ids_seen=set() if family=='ucdb' else None
    for df in _batches(src,batch_size):
        n=len(df)
        if src.id_field not in df:raise ValueError('Native provider ID field missing: '+src.id_field)
        ids=df[src.id_field].astype('string')
        if ids.isna().any():raise ValueError('Native provider has null IDs: '+src.layer)
        if ids_seen is not None:
            values=ids.to_numpy(dtype=str).tolist()
            if len(set(values))!=len(values) or set(values)&ids_seen:
                raise ValueError('UCDB duplicated entity IDs within a thematic layer: '+src.layer)
            ids_seen.update(values)
        target=out/'parts'/f'source_attributes_{offset:09d}.parquet'
        qc=target.with_suffix('.qc.json')
        if target.exists() and qc.exists():
            z=read_json(qc)
            if (z.get('job_id')!=jid or z.get('status')!='OK' or z.get('offset')!=offset
                or z.get('n_rows')!=n or pq.ParquetFile(target).metadata.num_rows!=n):
                raise ValueError('Existing native attribute part differs from provider '+str(target))
            parts.append(n);offset+=n;continue
        if target.exists() or qc.exists():
            raise FileExistsError('Unpaired native attribute part '+str(target))
        df=df.copy()
        df.insert(0,'cee_source_family',family)
        df.insert(1,'cee_source_layer',src.layer)
        df['cee_provider_id_string']=ids.to_numpy(dtype=str)
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.writing.parquet')
        df.to_parquet(tmp,index=False,compression='zstd')
        os.replace(tmp,target)
        write_json(qc,{'status':'OK','job_id':jid,'offset':offset,'n_rows':n,
                       'source_layer':src.layer,'native_id':src.id_field,
                       'all_original_fields_preserved':True})
        parts.append(n);offset+=n
        if offset%250000==0:print(f'[attributes-{family}] {src.layer} {offset}/{declared}',flush=True)
    if sum(parts)!=declared:raise ValueError('Native attributes conservation failure: '+src.layer)
    result={'status':'ALL_ORIGINAL_SOURCE_ATTRIBUTES_STREAMED',
            'family':family,'native_layer':src.layer,'native_id':src.id_field,
            'n_source_rows':sum(parts),'n_fields':len(src.fields),
            'this_is_source_entity_table_not_native_GF10_measurements':True}
    write_json(out/'run_qc.json',result)
    return result


def run(root,family,batch_size=50000):
    root=Path(root)
    if family not in ('ucdb','basin','admin0','admin1'):
        raise ValueError('Unknown original attribute family '+family)
    src=discover_family(root,family)
    base=root/'data/derived/cee_all_global_v2/native_attributes'/family
    if family!='ucdb':
        return _export_one(base,src,family,batch_size)

    # The multi-theme 2024 UCDB is NOT one ambiguous geometry layer. It has a
    # canonical geometry + independently keyed theme tables. Save ALL themes.
    themes=discover_ucdb_themes(root)
    from dataclasses import asdict
    out,jid=prepare_directory(base,{
       'geometry_source':asdict(src),
       'theme_sources':[asdict(z) for z in themes],
       'algorithm':'all_official_ucdb_themes_original_ids_v22'})
    summaries=[]
    for ix,theme in enumerate(themes,1):
        tag=re.sub('[^A-Za-z0-9_]+','_',theme.layer).strip('_')[:120]
        # prefix ensures uniqueness when two GPKGs contain same layer names.
        partdir=out/'themes'/f'{ix:03d}_{tag}'
        q=_export_one(partdir,theme,'ucdb',batch_size)
        summaries.append({'path':str(partdir),'native_id':theme.id_field,**q})
        print(f'[UCDB themes] {ix}/{len(themes)} {theme.layer}',flush=True)
    # A different provider ID between themes is reported rather than guessed
    # to be the same city ID; themes remain independently keyed.
    ids=sorted(set(x['native_id'] for x in summaries))
    result={'status':'ALL_ORIGINAL_UCDB_THEMES_STREAMED',
            'family':'ucdb','geometry_layer':src.layer,
            'n_theme_layers':len(summaries),'native_id_fields':ids,
            'id_alignment_verified':len(ids)==1,
            'themes':summaries,
            'entity_attributes_not_independent_GF10_measurements':True,
            'publication_ready':False}
    write_json(out/'run_qc.json',result)
    return result
