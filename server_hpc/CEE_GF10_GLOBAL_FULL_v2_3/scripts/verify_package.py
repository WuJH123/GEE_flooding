"""Offline integrity verification of this source archive after copying to Windows."""
from pathlib import Path
import hashlib,argparse,json

def verify(root):
    root=Path(root)
    m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for rel,ref in m['files'].items():
        p=root/rel
        if not p.is_file():raise FileNotFoundError(f'Package missing file {rel}')
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        if h!=ref['sha256']:raise ValueError(f'Package file altered {rel}')
    print('PACKAGE_SHA256_VERIFIED',len(m['files']),'files')
    return True

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True)
    a=ap.parse_args();verify(a.root)
