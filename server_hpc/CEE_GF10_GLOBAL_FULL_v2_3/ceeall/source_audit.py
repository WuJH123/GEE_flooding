"""Read-only audit of original user-confirmed GMTED mean-statistic products.

Do NOT silently replace a conflicting source description with user-provided
metadata. 'Mean' here is the declared input product type (based on the user's
confirmed download choice), not evidence of a verified product provenance.
"""
from pathlib import Path
import json
from .common import atomic_json,fidentity

NAMES={
  'elevation':'elevation_1KMmn_GMTEDmn.tif',
  'slope':'slope_1KMmn_GMTEDmd.tif',
  'roughness':'roughness_1KMmn_GMTEDmd.tif',
  'tpi':'tpi_1KMmn_GMTEDmd.tif',
  'tri':'tri_1KMmn_GMTEDmd.tif',
}

def gmted_audit(root):
    import rasterio
    root=Path(root);folder=root/'CEE数据'
    rows=[]
    for label,filename in NAMES.items():
        p=folder/filename
        if not p.is_file():
            raise FileNotFoundError(f'GMTED source missing: {p}')
        with rasterio.open(p) as ds:
            description='; '.join([d for d in ds.descriptions if d] +
                                  [f'{k}={v}' for k,v in ds.tags().items()])
            if ds.count!=1 or not ds.crs or not ds.crs.is_geographic or ds.transform.is_identity:
                raise ValueError(f'GMTED original source needs georeferenced single band: {p}')
            if any(abs(abs(v)-1/120)>0.0002 for v in ds.res):
                raise ValueError(f'GMTED expected 30-arcsecond resolution: {p}, got {ds.res}')
            conflict=any(s in description.lower() for s in ('maximum statistic','minimum statistic'))
            rows.append({'variable':label,'input':fidentity(p),'crs':str(ds.crs),
                'pixel_size_deg':list(ds.res),'shape':[ds.height,ds.width],
                'nodata':ds.nodata,'description':description[:800],
                'source_product_statistic':'MEAN_USER_CONFIRMED',
                'gf10_aggregation':'native_pixel_area_weighted_mean',
                'unit':'m' if label=='elevation' else 'SOURCE_UNIT_REVIEW_REQUIRED',
                'source_metadata_conflict':conflict,
                'publication_provenance_verified':False})
    out=root/'reports/cee_gmted_source_audit_v12.json'
    atomic_json(out,{'status':'GMTED_MEAN_CONTRACT_PILOT_AUDIT_NEEDS_SOURCE_DESCRIPTION_REVIEW',
       'official_product':'https://www.usgs.gov/coastal-changes-and-impacts/gmted2010',
       'files':rows,'n_files':len(rows),
       'metadata_conflict_count':sum(int(r['source_metadata_conflict']) for r in rows),
       'interpretation':'User confirms five mean-type downloads. Internal maximum descriptions are preserved and flagged.'})
    return {'n_files':len(rows),'metadata_conflicts':sum(x['source_metadata_conflict'] for x in rows),'report':str(out)}
