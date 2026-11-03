"""Automatic offline provider discovery of actual GDBs and UCDB multi-theme layers.

Scientific policy:
* FileGDB is a directory containing internal *.gdbtable files, not a ZIP
  extraction container coincidentally named *.gdb.
* HydroATLAS Basin level 07 is the default background resolution; levels are
  alternative catchment partitions, not independent rasters to be summed.
* GHS-UCDB has genuine THEMATIC layers. Use an explicit geometry hierarchy
  for urban footprint, export all theme attributes separately keyed by source
  provider ID. Never choose an arbitrary first tied theme.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass,asdict
import pyogrio

FAMILY_HINTS={
 'admin0':['geoboundariescgaz_adm0'],
 'admin1':['geoboundariescgaz_adm1'],
 'ucdb':['ghs_ucdb'],
 'basin':['basinatlas'],
 'river':['riveratlas'],
 'roads':['grip4_global_vector'],
}
PRIMARY_IDS={
 'admin0':['shapegroup','shapeid','iso3','iso_a3','adm0_a3'],
 'admin1':['shapeid','gid_1','adm1_code','iso_3166_2'],
 'ucdb':['id_uc_g0','id_hdc_g0','id_uc','uc_id','city_id','id'],
 'basin':['hybas_id','subbas_id','pfaf_id'],
 'river':['hyriv_id','riv_id','hydroriver_id'],
 'roads':['osm_id','road_id','id'],
}

@dataclass(frozen=True)
class Source:
    family:str
    path:str
    layer:str
    geometry_type:str
    count:int
    id_field:str|None
    native_crs:str
    fields:list[str]
    detected_from:str='provider_schema_v22'


def _real_gdb(p:Path)->bool:
    """Identify a real File Geodatabase, not a similarly named ZIP container."""
    if not p.is_dir() or p.suffix.lower()!='.gdb':return False
    try:
        # FileGDB stores a000000XX.gdbtable & matching metadata files.
        return any(q.is_file() and q.name.lower().endswith('.gdbtable')
                   for q in p.iterdir())
    except OSError:
        return False


def _file_sources(stage):
    stage=Path(stage)
    if not stage.exists():return []
    result=[]
    for p in stage.rglob('*'):
        # Reject the false HydroATLAS outer .gdb folders that contain another
        # real *.gdb plus catalog PDFs. OpenFileGDB cannot read those wrappers.
        if p.is_dir() and p.suffix.lower()=='.gdb':
            if _real_gdb(p):result.append(p)
            continue
        if p.is_file() and p.suffix.lower() in ('.shp','.gpkg','.fgb') and not any(
                a.suffix.lower()=='.gdb' for a in p.parents):
            result.append(p)
    return sorted(set(result))


def _hint(path,family):
    lower=str(path).lower().replace('\\','/')
    return any(term in lower for term in FAMILY_HINTS[family])


def _geometry_allowed(family,geometry):
    g=str(geometry).lower()
    if family in ('roads','river'):
        return 'line' in g or 'curve' in g
    return 'polygon' in g or 'surface' in g


def _make_source(family,path,layer,geom,info):
    fields=[str(x) for x in info.get('fields',[])]
    ident=next((actual for ideal in PRIMARY_IDS[family] for actual in fields
                if actual.lower()==ideal),None)
    cnt=info.get('features')
    cnt=int(cnt) if isinstance(cnt,(int,float)) and cnt>=0 else -1
    return Source(family,str(path),str(layer),str(geom),cnt,ident,
                  str(info.get('crs') or ''),fields)


def _candidates(root,family,include_nonspatial=False):
    if family not in FAMILY_HINTS:raise ValueError('Unknown family '+family)
    stage=Path(root)/'data/staged/cee_all'
    sources=[p for p in _file_sources(stage) if _hint(p,family)]
    if not sources:
        raise FileNotFoundError(f'No real staged source for {family}; searched {stage}. '
                                'ZIP container .gdb is NOT a real FileGDB; inspect nested folders.')
    results=[];bad=[]
    for p in sources:
        try:
            layers=pyogrio.list_layers(p)
        except Exception as exc:
            bad.append(f'{p}: {type(exc).__name__}: {exc}')
            continue
        for layer,geom in layers:
            if geom is None and not include_nonspatial:continue
            if geom is not None and not _geometry_allowed(family,geom):continue
            try:info=pyogrio.read_info(p,layer=layer)
            except Exception as exc:
                bad.append(f'{p} layer={layer}: {exc}')
                continue
            src=_make_source(family,p,layer,geom,info)
            results.append(src)
    if not results:
        raise ValueError('No supported geometry layers for '+family+'; inspect provider data. Errors: '+str(bad[:5]))
    # Read errors remain a warning if a valid FileGDB/layer was found. Never
    # let a spurious wrapper directory abort a correctly nested real source.
    return results


def _score(family,src):
    cname=src.layer.lower();pname=Path(src.path).name.lower()
    score=100 if src.id_field else -200
    if family=='basin':
        if re.search(r'lev0?7(?:$|\D)',cname):score+=160
        elif re.search(r'lev0?6(?:$|\D)',cname):score+=100
        elif re.search(r'lev0?8(?:$|\D)',cname):score+=75
        else:score-=100
    elif family=='river':
        if 'riveratlas' in cname:score+=60
    elif family=='roads':
        if 'grip' in cname or 'road' in cname:score+=60
    elif family=='ucdb':
        # Do NOT treat theme modules as a tie: they contain different city
        # attributes. For the geometry crosswalk prefer the dedicated overall
        # UCDB_GLOBE spatial layer, otherwise THEME_GEOGRAPHY, then GENERAL.
        if ('ghs_ucdb_globe' in cname or 'ghs_ucdb_globe' in pname) and 'theme' not in cname and 'theme' not in pname:
            score+=300
        elif 'theme_geography' in cname:score+=200
        elif 'theme_general_characteristics' in cname:score+=100
        elif 'theme_ghsl' in cname:score+=50
        else:score+=1
    elif family.startswith('admin'):
        if 'adm' in cname or 'caz' in cname:score+=15
    return score


def discover_family(root,family):
    allsrc=_candidates(root,family)
    scored=sorted(((_score(family,s),s) for s in allsrc),
                  key=lambda a:(-a[0],a[1].path,a[1].layer))
    best_score,best=scored[0]
    if len(scored)>1 and scored[1][0]==best_score:
        raise ValueError(f'Ambiguous provider geometry for {family}: '+
                         str([(s.layer,v) for v,s in scored[:8]]))
    if not best.native_crs:raise ValueError(f'Missing CRS {best.path}/{best.layer}')
    if family!='roads' and not best.id_field:
        raise ValueError(f'No documented stable ID field for {family}; fields={best.fields[:40]}')
    return best


def discover_ucdb_themes(root):
    """Return every local UCDB theme and spatial/nonspatial entity attributes.

    They must not all become independent GF10 polygons/indicators: associate
    their original attributes to stable UCDB IDs in independent source tables.
    """
    sources=_candidates(root,'ucdb',include_nonspatial=True)
    seen=set();out=[]
    for src in sources:
        k=(src.path,src.layer)
        if k in seen:continue
        seen.add(k)
        if not src.id_field:
            raise ValueError('UCDB thematic source lacks a known ID, refusing unkeyed attribute export: '+str(k))
        if src.count<0:raise ValueError('UCDB thematic source has unknown feature count: '+str(k))
        out.append(src)
    if not out:raise ValueError('No UCDB theme sources')
    return sorted(out,key=lambda s:(s.path,s.layer))


def discover_all(root):
    records={};errors={}
    for f in FAMILY_HINTS:
        try:records[f]=asdict(discover_family(root,f))
        except Exception as exc:errors[f]=str(exc)
    # Supplemental discoverability for all the original UCDB themes.
    if 'ucdb' not in errors:
        try:records['ucdb_attribute_layers']=[asdict(s) for s in discover_ucdb_themes(root)]
        except Exception as exc:errors['ucdb_attribute_layers']=str(exc)
    return {'sources':records,'errors':errors}
