"""Generate data dictionary FROM ACTUAL completed global output columns."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from .shared import write_json


def _column_meta(s):
    text=str(s).lower()
    if text in ('grid_id','grid_x','grid_y','land_area_km2'):
        return ('GF10_GSHHG', 'fixed spatial ID/area', '10km non-Antarctic','km2' if text=='land_area_km2' else 'id','FROZEN')
    if 'ghsl' in text or 'built_area' in text or 'population_count' in text or 'smod_' in text:
        unit='people' if 'pop' in text or 'population' in text else 'km2 or fraction by column suffix'
        return ('GHSL_R2023A','native 1km footprint-overlap original cell pixel', '2000 or 2020',unit,'NO_LAND_CLIP')
    if text.startswith('gmted_'):
        unit='m' if 'elevation' in text else 'UNVERIFIED_SOURCE_UNIT'
        return ('GMTED2010_Amatulli','30arcsec native area-weighted GF10 mean','static',unit,'ELEVATION_MAX_METADATA_CONFLICT')
    if text.startswith('wc2_') or 'worldclim' in text or text.startswith('wc_'):
        return ('WorldClim2.1','1970-2000 climate native pixel area-weighted GF10 mean','1970-2000','NATIVE_UNIT_PENDING_METADATA','NO_LAND_CLIP')
    if text.startswith('gisd_'):
        return ('GISD30','native historical 30m categorical GISD binary fraction','1985-2020','fraction of observed GISD cells','SOURCE_SEAM_COAST_QA_REQUIRED')
    if text.startswith('roads_'):
        return ('GRIP4_vector','actual network clipped to GF10; WGS84 geodesic','static','km or km/landkm2','NETWORK_SOURCE_COMPLETENESS_QA')
    if text.startswith('river_'):
        return ('RiverATLAS','actual river segments clipped to GF10; WGS84 geodesic','static','km or km/landkm2','HYDRO_SOURCE_COMPLETENESS_QA')
    if text.startswith(('admin0_','admin1_','ucdb_','basin_')):
        return ('Original_vector_provider','EPSG6933 full-cell source polygon area intersection','static','km2 or unitless','SOURCE_POLYGON_COAST_QA')
    if 'grip' in text:
        return ('GRIP4_density','5arcminute source density mean','static','m/km2 source native','5ARCMIN_COARSE_PROXY')
    return ('UNRESOLVED_PROVENANCE','see native source metadata','unknown','UNVERIFIED','DO_NOT_USE_WITHOUT_SOURCE_AUDIT')


def run(root):
    import pyarrow.parquet as pq
    root=Path(root)
    files=sorted((root/'data/derived/cee_all_global_v2/gf10_static_wide/tiles').glob('tile_*.parquet'))
    if len(files)!=715:raise ValueError('Static wide dictionary requires 715 fully generated output tiles')
    fields=pq.ParquetFile(files[0]).schema_arrow.names
    records=[]
    for col in fields:
        family,definition,epoch,unit,qa=_column_meta(col)
        records.append({'column':col,'source_family':family,'spatial_temporal_definition':definition,
                        'source_period':epoch,'unit':unit,'scientific_qa_flag':qa,
                        'is_daily_event_exposure':False,'publication_ready':False})
    dst=root/'data/derived/cee_all_global_v2/gf10_static_wide/indicator_dictionary.csv'
    pd.DataFrame(records).to_csv(dst,index=False,encoding='utf-8-sig')
    write_json(dst.with_suffix('.json'),{'n_columns':len(records),'source_specific_units_pending':sum(x['unit'].startswith('UNVERIFIED') or 'PENDING' in x['unit'] for x in records),
          'not_all_attrs_are_10km_measured':True,'event_climate_excluded':True,
          'external_QA_required_before_publication':True})
    return {'dictionary':str(dst),'n_fields':len(records)}
