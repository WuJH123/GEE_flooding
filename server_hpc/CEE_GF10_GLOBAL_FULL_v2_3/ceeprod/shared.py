from __future__ import annotations
from pathlib import Path
import json,hashlib,os,time

def read_json(f):return json.loads(Path(f).read_text(encoding='utf8'))
def write_json(f,v):
 p=Path(f);p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_name(p.name+'.writing');tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf8');os.replace(tmp,p)
def job_hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,default=str).encode()).hexdigest()
def file_identity(f):
    p=Path(f)
    if p.is_dir():
        # A FileGDB is a directory; directory stat alone does not capture
        # modifications of its internal *.gdbtable / *.gdbtablx files.
        files=sorted(q for q in p.rglob('*') if q.is_file())
        if not files:raise ValueError('Empty provider FileGDB directory: '+str(p))
        members=[(q.relative_to(p).as_posix(),q.stat().st_size,q.stat().st_mtime_ns) for q in files]
        return {'path':str(p.resolve()),'kind':'filegdb_directory',
                'n_members':len(members),'total_bytes':sum(z[1] for z in members),
                'max_mtime_ns':max(z[2] for z in members),
                'members_digest':job_hash(members)}
    s=p.stat()
    return {'path':str(p.resolve()),'size':s.st_size,'mtime_ns':s.st_mtime_ns}
def prepare_directory(out,spec):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);jid=job_hash(spec);manifest=p/'job.json'
 if manifest.exists():
  if read_json(manifest).get('job_id')!=jid:raise ValueError('Existing output belongs to DIFFERENT source/version: '+str(p))
 elif any(p.iterdir()):raise FileExistsError('Untracked partially written output at '+str(p))
 else:write_json(manifest,{'job_id':jid,'spec':spec})
 return p,jid
