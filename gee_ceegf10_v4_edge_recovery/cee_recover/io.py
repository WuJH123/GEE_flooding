"""Immutable on-disk provenance with atomic updates and strict resumption."""
import json,hashlib,os,pathlib,tempfile,datetime

def load(path,default=None):
    p=pathlib.Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def atomic(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+'.writing')
    with t.open('w',encoding='utf-8') as o:
        json.dump(value,o,indent=2,ensure_ascii=False,allow_nan=False)
        o.flush();os.fsync(o.fileno())
    os.replace(t,p)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def frozen_copy(source,target):
    p=pathlib.Path(target)
    if p.exists():
        if sha(source)!=sha(target):raise FileExistsError('Historical v3 source changed; do not overwrite: '+str(p))
        return str(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    import shutil
    shutil.copy2(source,p)
    if sha(source)!=sha(p):raise RuntimeError('Input snapshot SHA mismatch')
    return str(p)
