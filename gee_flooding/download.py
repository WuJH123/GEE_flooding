"""Official Zenodo download with MD5 and atomic destination verification."""
import hashlib
from pathlib import Path
import requests
from .paths import safe_output,atomic_json

API='https://zenodo.org/api/records/18647054'

def download_groundsource(root):
    target=safe_output(root,'data/raw/groundsource_2026.parquet')
    target.parent.mkdir(parents=True,exist_ok=True)
    r=requests.get(API,timeout=30);r.raise_for_status()
    records=[f for f in r.json()['files'] if f['key']=='groundsource_2026.parquet']
    if len(records)!=1:raise RuntimeError('Unexpected Zenodo file list; no guessed download')
    record=records[0];url=record['links']['self']; expected=record.get('checksum','')
    if target.is_file():
        _verify(target,expected)
        print('[REUSE verified]',target);return target
    partial=target.with_suffix('.parquet.partial');h=hashlib.md5()
    try:
        with requests.get(url,stream=True,timeout=(30,120)) as response:
            response.raise_for_status()
            with partial.open('wb') as out:
                for block in response.iter_content(4*1024*1024):
                    if block:out.write(block);h.update(block)
        if expected.startswith('md5:') and h.hexdigest()!=expected[4:]:
            raise ValueError('Zenodo MD5 mismatch, incomplete/corrupt download')
        partial.replace(target)
    except Exception:
        if partial.exists():partial.unlink()
        raise
    atomic_json(safe_output(root,'reports/qc/download_source.json'),
                {'source_url':API,'file':str(target),'md5':h.hexdigest(),
                 'size_bytes':target.stat().st_size,'source_license':'CC BY 4.0'})
    return target

def _verify(path,expected):
    if expected.startswith('md5:'):
        md5=hashlib.md5()
        with open(path,'rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''):md5.update(block)
        if md5.hexdigest()!=expected[4:]:raise ValueError('Existing file MD5 mismatch')
