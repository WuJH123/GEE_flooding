"""Assign ORIGINAL Groundsource geocoder polygons to EPSG:6933 GF10 cells.

A geocoded news polygon is NEVER assumed to be measured flood extent.
One raw observation has at most one primary cell; rejected rows are audited.
"""
from collections import Counter
from pathlib import Path
from math import ceil,floor
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import box
from shapely.ops import transform
from .paths import safe_output,atomic_json,check_raw_groundsource

CELL=10000

def intersect_cells(geom,allowed,projection,max_bbox=64):
    if geom is None or geom.is_empty or not geom.is_valid:
        return [],'INVALID_GEOMETRY'
    if geom.geom_type not in ('Polygon','MultiPolygon') or geom.area<=0:
        return [],'NOT_AREA_GEOMETRY'
    bx=geom.bounds
    if bx[2]-bx[0]>180:
        return [],'ANTIMERIDIAN_REQUIRES_REVIEW'
    try:
        g=transform(projection.transform,geom)
        if not g.is_valid or g.area<=0:return [],'INVALID_PROJECTED_GEOMETRY'
        x0,y0,x1,y1=g.bounds
        a,b=int(floor(x0/CELL)),int(ceil(x1/CELL))-1
        c,d=int(floor(y0/CELL)),int(ceil(y1/CELL))-1
        if (b-a+1)*(d-c+1)>max_bbox:return [],'GEOCODE_TOO_BROAD'
        candidates=[]
        for x in range(a,b+1):
            for y in range(c,d+1):
                gid=f'{x}_{y}'
                if gid not in allowed:continue
                frac=g.intersection(box(x*CELL,y*CELL,(x+1)*CELL,(y+1)*CELL)).area/g.area
                if frac>0:candidates.append((gid,float(frac)))
        if not candidates:return [],'NOT_IN_GF10_URBAN_DOMAIN'
        return sorted(candidates,key=lambda x:(-x[1],x[0])),'MATCHED'
    except (ValueError,OverflowError):return [],'TRANSFORM_FAILURE'

def classify(n,overlap):
    if n<=4 and overlap>=0.5:return 'HIGH_GEOCODE_SPECIFICITY'
    if n<=16 and overlap>=0.2:return 'MEDIUM_GEOCODE_SPECIFICITY'
    return 'LOW_GEOCODE_SPECIFICITY'

def build_labels(root,source,grid,grid_qc,batch_size=10000,max_bbox=64,
                 start='2000-01-01',end='2025-12-31'):
    """Read sources without changing them; write everything under the new root."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    import json
    source=check_raw_groundsource(source)
    qc=json.loads(Path(grid_qc).read_text(encoding='utf-8'))
    if qc.get('status')!='PASS_10KM_GRID_CONTRACT':
        raise RuntimeError('Frozen GF10 input has not passed Stage62b QC')
    frame=pd.read_parquet(grid,columns=['grid_id','grid_x','grid_y'])
    if frame.grid_id.duplicated().any():raise ValueError('Duplicate GF10 IDs')
    if any(f'{int(x)}_{int(y)}'!=str(z) for x,y,z in zip(frame.grid_x,frame.grid_y,frame.grid_id)):
        raise ValueError('Grid ID vs projected x/y mismatch')
    allowed=set(frame.grid_id.astype(str))
    output=safe_output(root,'outputs/labels/groundsource_gf10_primary.parquet')
    audit=safe_output(root,'outputs/labels/geocode_event_audit.parquet')
    if output.exists() or audit.exists():
        raise FileExistsError('Output exists: protect previous research results and use a new root/version')
    output.parent.mkdir(parents=True,exist_ok=True)
    schema=pa.schema([('event_id',pa.string()),('grid_id',pa.string()),
                      ('date',pa.date32()),('n_candidate_cells',pa.int16()),
                      ('primary_overlap',pa.float64()),('geocode_quality',pa.string())])
    aschema=pa.schema([('event_id',pa.string()),('date',pa.date32()),
                       ('status',pa.string()),('reported_area_km2',pa.float64()),
                       ('n_candidate_cells',pa.int16()),('geocode_quality',pa.string())])
    tmp=output.with_suffix('.parquet.partial');atmp=audit.with_suffix('.parquet.partial')
    writer=pa.parquet.ParquetWriter(tmp,schema,compression='zstd')
    awriter=pa.parquet.ParquetWriter(atmp,aschema,compression='zstd')
    stats=Counter();quality=Counter();n=0
    trans=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True)
    raw=pq.ParquetFile(source)
    try:
        for batch in raw.iter_batches(batch_size=batch_size,
                                      columns=['uuid','geometry','start_date','end_date','area_km2']):
            frame=batch.to_pandas()
            mapped=[];auditrows=[]
            for r in frame.itertuples(index=False):
                n+=1;event_id=str(r.uuid)
                date=pd.to_datetime(r.start_date,errors='coerce')
                status='INVALID_DATE';cand=[];qual='NOT_ELIGIBLE'
                if pd.notna(date):
                    date=date.date()
                    if not pd.Timestamp(start).date()<=date<=pd.Timestamp(end).date():status='OUTSIDE_PERIOD'
                    else:
                        try:g=wkb.loads(bytes(r.geometry)) if r.geometry is not None else None
                        except (ValueError,TypeError):g=None
                        cand,status=intersect_cells(g,allowed,trans,max_bbox)
                        if cand:
                            qual=classify(len(cand),cand[0][1])
                            mapped.append({'event_id':event_id,'grid_id':cand[0][0],
                                           'date':date,'n_candidate_cells':len(cand),
                                           'primary_overlap':cand[0][1],'geocode_quality':qual})
                else:date=None
                auditrows.append({'event_id':event_id,'date':date,'status':status,
                                  'reported_area_km2':float(r.area_km2) if r.area_km2 is not None else None,
                                  'n_candidate_cells':len(cand),'geocode_quality':qual})
                stats[status]+=1;quality[qual]+=1
            writer.write_table(pa.Table.from_pylist(mapped,schema=schema))
            awriter.write_table(pa.Table.from_pylist(auditrows,schema=aschema))
            if n%(batch_size*20)==0:print('[Groundsource processed]',n,dict(stats),flush=True)
        if n!=raw.metadata.num_rows:raise RuntimeError('Parquet scan incomplete')
    except Exception:
        writer.close();awriter.close()
        for p in (tmp,atmp):p.unlink(missing_ok=True)
        raise
    writer.close();awriter.close()
    tmp.replace(output);atmp.replace(audit)
    if sum(stats.values())!=n:raise RuntimeError('Audit cardinality mismatch')
    qc={'status':'PASS_LABEL_GEOCODE_AUDIT','rows_processed':n,
        'count_by_status':dict(stats),'count_by_quality':dict(quality),
        'grid_cells':len(allowed),'analysis_start':start,'analysis_end':end,
        'raw_source':str(source),'grid_source':str(grid),'max_bbox_cells':max_bbox,
        'note':'Geocoded news polygons are not verified flood extents or flood locations; HIGH is a geometry proxy'}
    atomic_json(safe_output(root,'reports/qc/labels_qc.json'),qc)
    return qc
