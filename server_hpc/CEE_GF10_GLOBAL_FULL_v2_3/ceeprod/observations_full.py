"""Full Groundsource parquet streaming, report location—not inundation extent.

No negative labels, no event-day flooding ground truth asserted. Retains original
UUID/date and records a representative mapped GF10 where a source geometry
is parseable in WGS84. Memory capped by pyarrow scanner batches.
"""
from __future__ import annotations
from pathlib import Path
import os, json,math
import numpy as np
import pandas as pd
from .shared import prepare_directory,write_json,file_identity


def _geometries(values):
    from shapely import from_wkb,from_wkt
    from shapely.geometry import shape
    import shapely
    out=[]
    for value in values:
        if isinstance(value,(bytes,bytearray,memoryview)):
            try:out.append(from_wkb(bytes(value)))
            except Exception:out.append(None)
        elif isinstance(value,str):
            try:
                if value.startswith('{'):out.append(shape(json.loads(value)))
                elif value[:2].lower() in ('01','00') and len(value)>12:
                    out.append(from_wkb(bytes.fromhex(value)))
                else:out.append(from_wkt(value))
            except Exception:out.append(None)
        elif isinstance(value,dict):
            try:out.append(shape(value))
            except Exception:out.append(None)
        else:out.append(None)
    return np.asarray(out,dtype=object)


def run(root,batchsize=40000):
    import pyarrow.parquet as pq
    from pyproj import Transformer
    import shapely
    root=Path(root)
    src=root/'data/raw/groundsource/groundsource_2026.parquet'
    if not src.is_file():raise FileNotFoundError('Original Zenodo Groundsource parquet missing '+str(src))
    schema=pq.ParquetFile(src).schema_arrow
    cols=set(schema.names)
    required={'uuid','geometry','start_date','end_date'}
    if not required<=cols:
        raise ValueError('Groundsource raw source schema differs from frozen reference '+str(sorted(required-cols)))
    frozen=pd.read_parquet(root/'gf10_global_nonantarctic_land.parquet',columns=['grid_id','grid_x','grid_y'])
    identities=frozen[['grid_x','grid_y','grid_id']].set_index(['grid_x','grid_y'])
    # Native GeoParquet metadata is preferred. If absent mark CRS as assumed
    # after a plausibility check; NEVER call news footprint a hydraulic mask.
    geocrs='WGS84_GEOMETRY_ASSUMED_FROM_GROUNDSOURCE_CONTRACT'
    meta=schema.metadata or {}
    if b'geo' in meta:
        try:
            g=json.loads(meta[b'geo'].decode())
            geocrs='GEOPARQUET_'+str(g.get('columns',{}).get('geometry',{}).get('crs',{}))[:160]
        except Exception:pass
    out,jid=prepare_directory(root/'data/derived/cee_all_global_v2/groundsource_reports',
         {'source':file_identity(src),'grid':file_identity(root/'gf10_global_nonantarctic_land.parquet'),
          'method':'stream_original_news_geocoding_representative_GF10_v2'})
    scan=pq.ParquetFile(src)
    tr=Transformer.from_crs(4326,6933,always_xy=True)
    inputcols=[x for x in ('uuid','geometry','start_date','end_date','area_km2') if x in cols]
    totals={'input_rows':0,'valid_geometries':0,'mapped_representative_grid':0,'unmapped_or_bad':0}
    for index,batch in enumerate(scan.iter_batches(batch_size=batchsize,columns=inputcols)):
        dst=out/'parts'/f'report_batch_{index:05d}.parquet'
        qc=dst.with_suffix('.qc.json')
        if dst.exists() and qc.exists():
            saved=json.loads(qc.read_text(encoding='utf8'))
            if saved.get('job_id')!=jid or saved.get('status')!='OK':
                raise ValueError('Groundsource prior batch mismatches job: '+str(dst))
            import pyarrow.parquet as pq2
            if pq2.ParquetFile(dst).metadata.num_rows!=saved['n_rows']:
                raise ValueError('Groundsource cached batch invalid: '+str(dst))
            for k in totals:totals[k]+=saved[k]
            continue
        if dst.exists() or qc.exists():raise FileExistsError('Groundsource orphan output '+str(dst))
        df=batch.to_pandas()
        shape_array=_geometries(df.geometry.to_numpy())
        valid=np.asarray([g is not None and not g.is_empty and g.is_valid for g in shape_array])
        coords_lon=np.full(len(df),np.nan);coords_lat=np.full(len(df),np.nan)
        for i,g in enumerate(shape_array):
            if valid[i]:
                pt=g.representative_point()
                coords_lon[i]=pt.x;coords_lat[i]=pt.y
        valid &= np.isfinite(coords_lon)&np.isfinite(coords_lat)&(np.abs(coords_lon)<=180)&(np.abs(coords_lat)<=90)
        xx=np.full(len(df),np.nan);yy=np.full(len(df),np.nan)
        if valid.any():
            a,b=tr.transform(coords_lon[valid],coords_lat[valid])
            xx[valid]=np.floor(np.asarray(a)/10000)
            yy[valid]=np.floor(np.asarray(b)/10000)
        query=pd.DataFrame({'grid_x':xx,'grid_y':yy})
        query['grid_x']=query.grid_x.astype('Int64');query['grid_y']=query.grid_y.astype('Int64')
        joined=query.merge(frozen[['grid_x','grid_y','grid_id']],how='left',on=['grid_x','grid_y'],validate='many_to_one',sort=False)
        if len(joined)!=len(df):raise ValueError('Groundsource representative location mapping lost records')
        result=pd.DataFrame({'uuid':df.uuid.astype(str).to_numpy(),
           'source_start_date':pd.to_datetime(df.start_date,errors='coerce',utc=True),
           'source_end_date':pd.to_datetime(df.end_date,errors='coerce',utc=True),
           'representative_grid_id':joined.grid_id.to_numpy(),
           'source_geometry_valid':valid,'not_physical_inundation':np.ones(len(df),dtype=bool)})
        if 'area_km2' in df:result['source_geocoding_geometry_area_km2']=pd.to_numeric(df.area_km2,errors='coerce')
        dst.parent.mkdir(parents=True,exist_ok=True)
        tmp=dst.with_suffix('.writing.parquet');result.to_parquet(tmp,index=False,compression='zstd');os.replace(tmp,dst)
        counts={'input_rows':len(result),'valid_geometries':int(valid.sum()),
               'mapped_representative_grid':int(result.representative_grid_id.notna().sum()),
               'unmapped_or_bad':int(result.representative_grid_id.isna().sum())}
        for k in totals:totals[k]+=counts[k]
        write_json(qc,{'job_id':jid,'status':'OK','n_rows':len(result),**counts,
          'geocoded_footprint_not_actual_flood_extent':True,'crs_source':geocrs})
        print(f'[Groundsource] {index+1} batches, {totals["input_rows"]:,} reports',flush=True)
    if totals['input_rows']!=scan.metadata.num_rows:
        raise ValueError('Groundsource full original record count not conserved')
    write_json(out/'run_qc.json',{'status':'ALL_ORIGINAL_GROUNDSOURCE_REPORTS_INDEXED_NOT_FLOOD_EXTENT',
        **totals,'source_crs':geocrs,'not_negative_labels':True,'publication_ready_as_physical_inundation':False})
    return totals
