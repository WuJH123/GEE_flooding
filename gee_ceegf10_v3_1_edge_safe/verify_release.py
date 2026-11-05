"""Verify the immutable offline release contents without contacting the network."""
from pathlib import Path
import hashlib,json,sys
p=Path(__file__).resolve().parent
m=json.loads((p/'SHA256_MANIFEST.json').read_text(encoding='utf8'))
for rel,expected in m['sha256'].items():
    f=p/rel
    if not f.is_file():raise SystemExit('MISSING release file: '+rel)
    if hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
        raise SystemExit('MISMATCH release SHA256: '+rel)
print('RELEASE_SHA256_PASS',len(m['sha256']),'files')
