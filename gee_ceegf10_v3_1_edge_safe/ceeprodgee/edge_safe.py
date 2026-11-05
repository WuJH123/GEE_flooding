"""Safe EPSG:6933 boundary exports and immutable rejected-output reconciliation.

No GEE request occurs in this module. Never use this to reclassify an
unverified output as scientifically accepted.
"""
from __future__ import annotations
import csv,hashlib,math
from pathlib import Path
from .contract import MERIT_BANDS


BAD_ACK='REJECT_3474X10_EXPORT'
KNOWN_BAD_KEY='merit_-1740_-240_10'


def next_attempt_key(records,key):
    known={r['key'] for r in records}
    for i in range(1,100):
        name=f'{key}_edgefix{i}'
        if name not in known:return name
    raise ValueError('Too many edge retries; inspect history')


def validate_reject_and_quarantine(entries,key,ack,observed_tif=None):
    """Quarantine only the one user-evidenced malformed tile; retain original record.

    When the GeoTIFF is provided, verify width/height directly. When not,
    require the exact 3474x10 human acknowledgment and record as unverified.
    """
    if key!=KNOWN_BAD_KEY or ack!=BAD_ACK:
        raise ValueError('Only the previously audited malformed west-edge task may be quarantined')
    old=[r for r in entries if r.get('key')==key]
    if len(old)!=1 or old[0].get('local_qc_pass') or old[0].get('state') not in ('SUCCEEDED','COMPLETED'):
        raise ValueError('No single terminal, QC-rejected matching task to quarantine')
    record=old[0]
    actual=None
    if observed_tif:
        import rasterio
        with rasterio.open(observed_tif) as ds:
            actual=[ds.width,ds.height]
        if actual!=[3474,10]:
            raise ValueError(f'Unexpected damaged export shape: {actual}; refusing quarantine')
    if record.get('superseded_by'):
        raise ValueError('Old task already quarantined; use existing replacement key')
    retry=next_attempt_key(entries,key)
    record['quarantine']={
        'reason':'EPSG6933_WEST_EDGE_FULL_RECTANGLE_GEO_SPAN_3474x10',
        'observed_width_height':actual if actual else [3474,10],
        'observed_from_source':'RASTERIO_VERIFIED' if actual else 'EXPLICIT_USER_REPORTED_NOT_FILE_VERIFIED',
        'original_qc_pass':False,
        'do_not_use_data':True,
    }
    record['superseded_by']=retry
    return retry


def guarded_previous_tasks(entries,live_status):
    """Non-superseded tasks must have terminal success and accepted local QC.

    Quarantined tasks only bypass the guard if a replacement is present and
    itself is locally accepted. Exception: an about-to-be-submitted replacement
    must be deliberately executed from the explicit repair command.
    """
    lookup={r.get('key'):r for r in entries}
    for rec in entries:
        successor=rec.get('superseded_by')
        if successor:
            next_record=lookup.get(successor)
            if not next_record or not next_record.get('local_qc_pass'):
                raise RuntimeError('Superseded task replacement has no approved QC: '+str(successor))
            continue
        state=live_status(rec)
        if state.get('state') not in ('SUCCEEDED','COMPLETED'):
            raise RuntimeError(f"Prior job pending/failed, cannot submit: {rec.get('key')} ({state.get('state')})")
        if not rec.get('local_qc_pass'):
            raise RuntimeError('Prior export not locally accepted: '+str(rec.get('key')))


def check_edge_csv(path,expected_ids,bands=MERIT_BANDS):
    path=Path(path)
    if not path.is_file():raise FileNotFoundError(path)
    expected=set(str(x) for x in expected_ids)
    if not expected:raise ValueError('No expected GF10 IDs')
    rows=[]
    with path.open('r',encoding='utf-8-sig',newline='') as fh:
        reader=csv.DictReader(fh)
        headers=set(reader.fieldnames or ())
        if not set(['grid_id',*bands]).issubset(headers):
            raise ValueError('CSV does not contain the frozen band order and grid_id')
        for r in reader:
            if not r.get('grid_id'):raise ValueError('CSV row missing GF10 identifier')
            d={'grid_id':r['grid_id']}
            for name in bands:
                raw=(r.get(name) or '').strip()
                if not raw or raw.lower() in ('null','nan') or (raw and abs(float(raw)+9999.)<1e-6):d[name]=float('nan')
                else:
                    v=float(raw)
                    if not math.isfinite(v):raise ValueError('Nonfinite nonmissing raster value: '+name)
                    d[name]=v
            rows.append(d)
    ids=[r['grid_id'] for r in rows]
    if len(ids)!=len(expected) or len(ids)!=len(set(ids)) or set(ids)!=expected:
        raise ValueError(f'CSV does not exactly match expected land GF10 IDs; actual={len(ids)}, expected={len(expected)}')
    finite=lambda r,k:math.isfinite(r[k])
    accepted=0
    for r in rows:
        for k in ('merit_valid_fraction','merit_permanent_water_fraction',
                  'merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid',
                  'merit_hand_le10_fraction_valid','merit_slope_le2_fraction_valid'):
            if finite(r,k) and not -1e-4<=r[k]<=1.0001:
                raise ValueError('Out-of-range MERIT fraction: '+k)
        a,b,c='merit_hand_le2_fraction_valid','merit_hand_le5_fraction_valid','merit_hand_le10_fraction_valid'
        if all(finite(r,k) for k in (a,b,c)) and (r[a]>r[b]+1e-5 or r[b]>r[c]+1e-5):
            raise ValueError('HAND area thresholds not monotone')
        a,b,c='merit_hand_p10_m','merit_hand_p50_m','merit_hand_p90_m'
        if all(finite(r,k) for k in (a,b,c)) and (r[a]>r[b]+.001 or r[b]>r[c]+.001):
            raise ValueError('HAND quantiles not ordered')
        m,q='merit_upa_max_km2','merit_upa_p90_km2'
        if all(finite(r,k) for k in (m,q)) and r[m]+.01<r[q]:
            raise ValueError('UPA maximum below p90')
        k='merit_upa_max_log1p'
        if all(finite(r,z) for z in (m,k)) and abs(r[k]-math.log1p(max(0,r[m])))>.001:
            raise ValueError('UPA log1p not conserved')
        if finite(r,'merit_valid_fraction') and r['merit_valid_fraction']>0:accepted+=1
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'status':'EDGE_CSV_QC_PASS_NEEDS_PHYSICAL_QA','file':str(path),
            'n_land_ids':len(expected),'n_source_valid':accepted,
            'grid_ids_sha256':hashlib.sha256('\n'.join(sorted(expected)).encode()).hexdigest(),
            'sha256':digest,'n_bands':len(bands),
            'publication_ready':False,
            'note':'CSV values are frozen GF10 pixel centres; projection-domain partial cells require separate verification.'}


def compact_merge_rows(rows):
    """Cross-output merge helper: no row is accepted twice."""
    all_ids=set()
    for block in rows:
        ids=set(block)
        if len(ids)!=len(block) or ids & all_ids:raise ValueError('Duplicate GF10 IDs in combined sources')
        all_ids|=ids
    return all_ids


def accepted_static_records(records,family):
    """Event-method rows have no `family`; never let them crash MERIT merge."""
    return [r for r in records if r.get('family')==family and r.get('local_qc_pass') is True]
