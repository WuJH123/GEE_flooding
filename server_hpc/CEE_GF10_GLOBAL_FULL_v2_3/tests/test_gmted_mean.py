from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from ceeall.source_audit import gmted_audit,NAMES

def test_all_five_user_confirmed_mean_with_conflict_report(tmp_path):
    root=tmp_path/'root';src=root/'CEE数据';src.mkdir(parents=True)
    for label,filename in NAMES.items():
        with rasterio.open(src/filename,'w',driver='GTiff',width=12,height=12,
            count=1,crs='EPSG:4326',dtype='float32',nodata=-32768,
            transform=from_origin(0,12/120,1/120,1/120)) as ds:
            ds.write(np.full((12,12),14,dtype='float32'),1)
            if label=='elevation':ds.set_band_description(1,'Maximum Statistic')
    result=gmted_audit(root)
    assert result['n_files']==5 and result['metadata_conflicts']==1
    import json
    report=json.loads(Path(result['report']).read_text('utf8'))
    assert all(x['source_product_statistic']=='MEAN_USER_CONFIRMED' for x in report['files'])
    assert report['status'].startswith('GMTED_MEAN_CONTRACT')

def test_filename_mean_are_source_not_gf10_mean():
    assert NAMES['elevation']=='elevation_1KMmn_GMTEDmn.tif'
    assert NAMES['slope'].endswith('_GMTEDmd.tif')
