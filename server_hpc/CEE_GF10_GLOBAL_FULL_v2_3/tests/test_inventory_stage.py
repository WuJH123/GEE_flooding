from pathlib import Path
import zipfile,pytest
from ceeall.inventory import family,inventory
from ceeall.staging import stage_zip

def test_known_inventory_families():
    assert family('ERA5-EX v4.zip')=='era5ex'
    assert family('elevation_1KMmn_GMTEDmn.tif')=='gmted'
    assert family('GISD30_1985-2020_E0_E30.rar')=='gisd30'
    assert family('Worldclim.zip')=='unmapped'

def test_archive_safe_staging_and_reuse(tmp_path):
    src=tmp_path/'example.zip'
    with zipfile.ZipFile(src,'w') as z:
        z.writestr('wc2.1_30s_bio_1.tif',b'valid tiff mock')
        z.writestr('readme.txt','hello')
    out=tmp_path/'staged'
    r=stage_zip(src,out,pattern=r'\.(tif|txt)$')
    assert r['n_members']==2
    assert (out/'wc2.1_30s_bio_1.tif').read_bytes()==b'valid tiff mock'
    assert stage_zip(src,out,pattern=r'\.(tif|txt)$')['n_members']==2
    (out/'readme.txt').write_text('changed!')
    with pytest.raises((ValueError,FileExistsError),match='CRC mismatch|length differs'):
        stage_zip(src,out,pattern=r'\.(tif|txt)$')

def test_inventory_reads_real_zip_metadata(tmp_path):
    root=tmp_path/'raw';root.mkdir()
    with zipfile.ZipFile(root/'wc2.1_30s_bio.zip','w') as z:z.writestr('x.tif',b'abc')
    r=inventory(root,tmp_path/'inventory.csv')
    assert r['file_count']==1
    assert (tmp_path/'inventory.csv').exists()

def test_archive_path_traversal_refused(tmp_path):
    z=tmp_path/'bad.zip'
    with zipfile.ZipFile(z,'w') as zz:zz.writestr('../evil.txt','not allowed')
    with pytest.raises(ValueError,match='path traversal'):
        stage_zip(z,tmp_path/'out',pattern=r'\.txt$')
