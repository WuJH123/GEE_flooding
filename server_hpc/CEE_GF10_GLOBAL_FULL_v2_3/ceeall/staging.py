"""Safe, restartable extraction of locally downloaded archives (no external downloads)."""
from __future__ import annotations
from pathlib import Path
import os, subprocess, shutil, zipfile, tempfile, hashlib
from .common import fidentity, ensure_job,atomic_json,read_json

def stage_zip(source,out,pattern=None,cap_gb=45):
    import re
    p=Path(source);dest=Path(out)
    if not p.is_file():raise FileNotFoundError(p)
    with zipfile.ZipFile(p) as z:
        selected=[info for info in z.infolist() if not info.is_dir() and
                  (pattern is None or re.search(pattern,info.filename,re.I))]
        if not selected:raise ValueError('Archive lacks matching files: '+str(p))
        total=sum(x.file_size for x in selected)
        if total>cap_gb*1e9:raise ValueError('Decompressed selection exceeds cap_gb')
        j=ensure_job(dest,{'source':fidentity(p),'pattern':pattern,'stage_version':2})
        # v2.1: a prior source-identical, CRC-verified stage needs only a fast
        # member-size check, not an O(uncompressed-bytes) CRC reread on every
        # 715-shard production restart. The first stage still checks CRC.
        stamp=dest/'stage_qc.json'
        if stamp.exists():
            try:previous=read_json(stamp)
            except Exception:previous={}
            if (previous.get('status')=='ZIP_MEMBERS_CRC_VERIFIED' and
                previous.get('job_id')==j and previous.get('n_members')==len(selected) and
                all((dest/Path(x.filename.replace('\\','/'))).is_file() and
                    (dest/Path(x.filename.replace('\\','/'))).stat().st_size==x.file_size
                    for x in selected)):
                return {'status':'REUSED_CRC_VERIFIED_STAGE', 'n_members':len(selected),'out':str(dest)}
        # Only account for not-yet-extracted members: a cache hit must not
        # fail because the full original archive is larger than current free
        # space. Zip extracted members may be massive GeoTIFFs / FileGDBs.
        missing_bytes=sum(x.file_size for x in selected if not
            (dest/Path(x.filename.replace('\\','/'))).exists())
        if missing_bytes and shutil.disk_usage(dest).free<missing_bytes*1.10:
            raise OSError(f'Insufficient free disk capacity for missing ZIP members: '
                          f'need about {missing_bytes*1.10/1e9:.1f} GB')
        ready=0
        for info in selected:

            rel=Path(info.filename.replace('\\','/'))
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Archive path traversal '+str(rel))
            target=(dest/rel).resolve()
            if dest.resolve() not in target.parents:raise ValueError('Unsafe archive member')
            if target.exists():
                # Do not trust pre-existing output based on length alone, CRC is verified below.
                if target.stat().st_size!=info.file_size:raise FileExistsError('Existing member length differs '+str(target))
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                tmp=target.with_name(target.name+'.writing')
                with z.open(info) as src, open(tmp,'wb') as output:shutil.copyfileobj(src,output,8*1024*1024)
                os.replace(tmp,target)
            import zlib
            crc=0
            with target.open('rb') as check:
                for b in iter(lambda:check.read(8*1024*1024),b''):crc=zlib.crc32(b,crc)
            if crc & 0xffffffff!=info.CRC:raise ValueError('Archive CRC mismatch '+str(target))
            ready+=1
        atomic_json(dest/'stage_qc.json',{'status':'ZIP_MEMBERS_CRC_VERIFIED','job_id':j,'archive':str(p),
                   'n_members':ready,'bytes':total,'pattern':pattern})
        return {'n_members':ready,'out':str(dest)}

def _hash_file(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for buf in iter(lambda:stream.read(8*1024*1024),b''):
            h.update(buf)
    return h.hexdigest()


def stage_rar(source,out,sevenzip=None):
    """Safe resumable staging: no modifications to original RAR/derived data.

    Extract to a separate temporary directory, check 7-Zip CRC/exit status,
    compare existing files by checksum rather than silently overwriting them,
    and promote only verified source TIFFs to staged input. Existing v2
    successful stage manifests remain valid.
    """
    from ceeprod.doctor import sevenzip_executable
    p=Path(source);dest=Path(out)
    if not p.is_file() or p.suffix.lower()!='.rar':raise FileNotFoundError(source)
    exe=sevenzip or sevenzip_executable()
    if not exe:raise FileNotFoundError('7z.exe NOT FOUND: official Windows x64 7-Zip required. See https://www.7-zip.org/download.html')
    j=ensure_job(dest,{'source':fidentity(p),'stage_version':2})
    manifest=dest/'stage_qc.json'
    if manifest.exists():
        prev=read_json(manifest)
        if prev.get('job_id')==j and prev.get('status') in ('RAR_INTEGRITY_TEST_PASS','RAR_EXTRACT_COMPLETE_V21'):
            discovered=list(dest.rglob('*.tif'))
            if prev.get('n_tif')==len(discovered) and all(q.is_file() and q.stat().st_size>0 for q in discovered):
                if prev.get('files') and any(not (dest/v['name']).is_file() or
                         (dest/v['name']).stat().st_size!=v['bytes'] for v in prev['files']):
                    raise ValueError('Staged GISD30 file metadata changed after RAR integrity check: '+str(dest))
                return {'status':'REUSED_VERIFIED_RAR_STAGE','n_tif':len(discovered),'out':str(dest)}
            raise ValueError('Staged GISD30 archive directory changed since QC: '+str(dest))
    def invoke(argv):
        cp=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,errors='replace')
        if cp.returncode:
            raise RuntimeError('7-Zip '+str(argv[1])+' failed on '+p.name+
                               ' (exit='+str(cp.returncode)+'): '+cp.stdout[-6000:])
        return cp.stdout
    # Validate archived compressed bytes before writing any staged files.
    invoke([exe,'t','-y','-bso0','-bsp0',str(p)])
    scratch_base=dest.parents[2]/'working'/'cee_stage_scratch_v21'
    scratch_base.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix=p.stem+'_',dir=scratch_base))
    try:
        invoke([exe,'x','-y','-bso0','-bsp0',f'-o{tmp}',str(p)])
        files=sorted(q for q in tmp.rglob('*.tif') if q.is_file())
        if not files:raise ValueError('RAR contains no TIFF files: '+str(p))
        promoted=[]
        for q in files:
            rel=q.relative_to(tmp);target=dest/rel
            if target.exists():
                if target.stat().st_size!=q.stat().st_size or _hash_file(target)!=_hash_file(q):
                    raise FileExistsError('Source TIFF conflicts with existing partial staged file '+str(target)+
                                          '; nothing overwritten; inspect source before resuming')
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                os.replace(q,target)
            promoted.append({'name':rel.as_posix(),'bytes':target.stat().st_size})
        existing=sorted(q for q in dest.rglob('*.tif') if q.is_file())
        if len(existing)!=len(promoted):
            raise ValueError('Staging source has unexpected TIFFs beyond this archive; check folder '+str(dest))
        atomic_json(manifest,{'status':'RAR_EXTRACT_COMPLETE_V21','n_tif':len(promoted),
                    'job_id':j,'source':fidentity(p),'files':promoted})
        return {'status':'STAGED_RAR_CRC_AND_CHECKSUM_CHECKED','n_tif':len(promoted),'out':str(dest)}
    finally:
        # Scratch files are generated exclusively by this invocation;
        # source archive and existing verified staged data remain intact.
        shutil.rmtree(tmp,ignore_errors=True)

FAMILY_ARCHIVES={
 'worldclim':['wc2.1_30s_*.zip'],'era5ex':['ERA5-EX v4.zip'],
 'admin':['geoBoundariesCGAZ_ADM*.zip'],'ucdb':['GHS_UCDB*.zip'],
 'hydroatlas':['BasinATLAS_Data_v10.gdb.zip','RiverATLAS_Data_v10.gdb.zip'],
 'roads':['GRIP4_density_total.zip','GRIP4_global_vector_fgdb.zip'],
 'gisd':['GISD30_*.rar']}

def stage_family(src,dest,family,cap_gb=45,first=None):
    src=Path(src);dest=Path(dest)
    if family not in FAMILY_ARCHIVES:raise ValueError('Unknown family '+family)
    matches=[]
    for pat in FAMILY_ARCHIVES[family]:matches += list(src.glob(pat))
    if not matches:raise FileNotFoundError('No downloaded archives for '+family+' under '+str(src))
    matches=sorted(set(matches))
    if first is not None:matches=matches[:first]
    results=[]
    for p in matches:
        out=dest/p.stem
        if p.suffix.lower()=='.rar':results.append(stage_rar(p,out))
        else:
            regex=(r'\.nc$' if family=='era5ex' else
                   r'\.(tif|txt)$' if family=='worldclim' else
                   None if family in ('hydroatlas','roads','ucdb') else
                   r'\.(tif|asc|shp|shx|dbf|prj|cpg|gpkg|xlsx|txt|pdf)$')
            # Keep ALL native *.gdb internal files, including the .atx/.freelist
            # index files. A filename-extension allowlist corrupts FileGDBs.
            results.append(stage_zip(p,out,pattern=regex,cap_gb=cap_gb))
    return results
