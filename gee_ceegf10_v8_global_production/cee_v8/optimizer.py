"""Verified, bounded grouping of adjacent MERIT/Hydro v4 safe GF10 parents.

This module never calls Google Earth Engine. Groups are promoted only after a
real independent 16-band canary and measured EECU/time have passed. No synthetic
flood labels, no coastal fill, no projection wrap of quarantined seam cells.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import math
import re
import json
import hashlib

PARENT_RE = re.compile(r'^merit_(-?\d+)_(-?\d+)_10$')
TILE_SIZE = 10
GRID_PIXEL_METERS = 10_000
MERIT_APPROX_PIXEL_METERS = 92.77
HALO_METERS = 80_000


def _xy(r):
    m = PARENT_RE.fullmatch(str(r['tile_key']))
    if m is None:
        raise ValueError('Unrecognized frozen parent tile key: ' + str(r['tile_key']))
    return int(m.group(1)), int(m.group(2))


def _ids(row):
    s = row['land_ids']
    if not isinstance(s, str) or not s:
        raise ValueError('Original GF10 land membership absent')
    z = s.split(';')
    if len(z) != len(set(z)) or len(z) != int(row['n_land_cells']):
        raise ValueError('Corrupt original source GF10 land membership')
    return z


def _work_mpix(w, h):
    return ((w*GRID_PIXEL_METERS+2*HALO_METERS) *
            (h*GRID_PIXEL_METERS+2*HALO_METERS) /
            MERIT_APPROX_PIXEL_METERS**2 / 1e6)


def _rect(children):
    x0=min(int(z['crop_x0']) for z in children)
    y0=min(int(z['crop_y0']) for z in children)
    x1=max(int(z['crop_x0'])+int(z['width']) for z in children)
    y1=max(int(z['crop_y0'])+int(z['height']) for z in children)
    return x0,y0,x1-x0,y1-y0


def _group_rows(children, factor, label=None):
    x,y,w,h=_rect(children)
    ids=[]
    for z in children: ids.extend(_ids(z))
    if len(ids)!=len(set(ids)):
        raise ValueError('GF10 member duplicated by MERIT group')
    for gid in ids:
        gx,gy=map(int,gid.split('_'))
        if not x<=gx<x+w or not y<=gy<y+h:
            raise ValueError('Land cell not within merged exact source GF10 crop')
    digest=hashlib.sha256('|'.join(sorted(ids)).encode('ascii')).hexdigest()[:16]
    key=label or f'M9F{factor}_{x}_{y}_{digest}'
    return {'tile_key':key,'batch_id':key,'crop_x0':x,'crop_y0':y,
            'width':w,'height':h,'n_land_cells':len(ids),
            'land_ids':';'.join(sorted(ids)),
            'source_family':'MERIT_HYDRO_16_BANDS_80KM_BUFFER_PACKED',
            'parent_tiles':';'.join(sorted(str(z['tile_key']) for z in children)),
            'pack_factor':factor,
            'native_source_megapixels_estimate':round(_work_mpix(w,h),3)}


def pack_safe(rows, factor=4, min_density=0.22, max_native_mpix=42.0):
    """Group only spatially neighboring original 10x10 parents.

    This planner does NOT guarantee GEE runtime or EECU cost. It limits the
    extent of each potential 90m computation, and requires live canary approval
    before the planned tasks can be registered or submitted.
    """
    if factor not in (1,2,3,4):raise ValueError('Factor must be tested in 1,2,3,4')
    if not 0<min_density<=1:raise ValueError('Bad land density threshold')
    rows=[dict(r) for r in rows]
    original_keys=set()
    grouped=defaultdict(list)
    expected=[]
    for r in rows:
        a,b=_xy(r)
        if a%10 or b%10:raise ValueError('Not a frozen 10x10 aligned parent')
        if str(r['tile_key']) in original_keys:raise ValueError('Duplicate source parent')
        original_keys.add(str(r['tile_key']))
        expected.extend(_ids(r))
        grouped[(a//(factor*10),b//(factor*10))].append(r)
    if len(expected)!=len(set(expected)):
        raise ValueError('Original source repeats GF10 membership')
    output=[]
    for group in grouped.values():
        if len(group)==1 or factor==1:
            output.extend(_group_rows([r],1) for r in group)
            continue
        candidate=_group_rows(group,factor)
        pixels=candidate['width']*candidate['height']
        dens=candidate['n_land_cells']/pixels
        if (candidate['width']>factor*10 or candidate['height']>factor*10
                or candidate['native_source_megapixels_estimate']>max_native_mpix
                or dens<min_density):
            output.extend(_group_rows([r],1) for r in group)
        else:output.append(candidate)
    actual=[]
    for z in output:actual.extend(_ids(z))
    if len(actual)!=len(expected) or set(actual)!=set(expected):
        raise ValueError('MERIT packing lost or invented source GF10 land cells')
    if len({z['batch_id'] for z in output})!=len(output):
        raise ValueError('Packed MERIT export collision')
    return output,{'n_original_parent_jobs':len(rows),'n_optimized_jobs':len(output),
                   'factor_requested':factor,'n_unique_land_cells':len(actual),
                   'reduction_factor':round(len(rows)/max(len(output),1),3),
                   'max_est_native_mpix':max((z['native_source_megapixels_estimate'] for z in output),default=0),
                   'has_independent_live_science_approval':False}


def split_packed_parent(packed, original_rows):
    """Replace one failed merged export by disjoint original-parent quadrants."""
    member=set(str(packed['parent_tiles']).split(';'))
    children=[dict(r) for r in original_rows if str(r['tile_key']) in member]
    if len(children)!=len(member):raise ValueError('Cannot find all original parents of failed pack')
    if len(children)<=1:raise ValueError('Cannot split original scientifically-validated parent')
    xs=[_xy(z)[0] for z in children];ys=[_xy(z)[1] for z in children]
    span_x=max(xs)-min(xs);span_y=max(ys)-min(ys)
    axis=0 if span_x>=span_y else 1
    values=sorted(set(xs if axis==0 else ys))
    if len(values)<=1:axis=1-axis;values=sorted(set(xs if axis==0 else ys))
    if len(values)<=1:raise ValueError('Coincident parents cannot split')
    cut=values[(len(values)-1)//2]
    a=[r for r in children if _xy(r)[axis]<=cut]
    b=[r for r in children if _xy(r)[axis]>cut]
    if not a or not b:raise ValueError('Empty packed child')
    l=_group_rows(a,len(a) and min(4,math.ceil(math.sqrt(len(a)))))
    r=_group_rows(b,len(b) and min(4,math.ceil(math.sqrt(len(b)))))
    original_ids=set(_ids(packed))
    child_ids=set(_ids(l))|set(_ids(r))
    if child_ids!=original_ids or set(_ids(l))&set(_ids(r)):
        raise ValueError('Packed failure fallback did not conserve original land')
    return [l,r]


def choose_factor_from_live(records,min_reference_cells=50,max_median_task_seconds=3600,
                            max_p95_rel=0.005,max_relative=0.02):
    """Only real GEE outputs compared to independent V7 source can approve size.

    records must contain source-image hashes, real task IDs, original source
    references, EECU, runtime and per-band error summaries. No pass if absent.
    """
    accepted=[]
    by=defaultdict(list)
    for x in records:
        if x.get('state')!='ACCEPTED' or not x.get('source_sha256') or not x.get('reference_sha256'):
            continue
        if not x.get('task_id') or not isinstance(x.get('eecu_h'),(float,int)):
            continue
        by[int(x['factor'])].append(x)
    for factor,group in by.items():
        if factor not in (1,2,3,4) or len(group)<3:continue
        if sum(int(x.get('reference_count',0)) for x in group)<min_reference_cells:continue
        if len(set(x['stratum'] for x in group))<3:continue
        if any(float(x['p95_rel'])>max_p95_rel or float(x['max_rel'])>max_relative
               or int(x['mask_mismatch'])!=0 or int(x['n_bad_bands'])>0 for x in group):continue
        durations=sorted(float(x['task_wall_seconds']) for x in group)
        if durations[len(durations)//2]>max_median_task_seconds or max(durations)>3*max_median_task_seconds:continue
        accepted.append(factor)
    return max(accepted,default=0)
