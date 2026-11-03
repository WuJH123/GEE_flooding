"""No-network local source discovery and safe selective ZIP extraction."""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import hashlib,os,re,shutil,zlib
import pandas as pd
from .core import json_write,read_json,file_identity

EXPECTED_PATTERNS={
 'ghsl_built2000':'GHS_BUILT_S_E2000*1000*.zip',
 'ghsl_built2020':'GHS_BUILT_S_E2020*1000*.zip',
 'ghsl_nres2020':'GHS_BUILT_S_NRES_E2020*1000*.zip',
 'ghsl_pop2020':'GHS_POP_E2020*1000*.zip',
 'ghsl_smod2020':'GHS_SMOD_E2020*1000*.zip',
 'groundsource':'groundsource_2026.parquet',
 'gmted_elevation':'elevation_1KMmn_GMTEDmn.tif',
 'gmted_slope':'slope_1KMmn_GMTEDmd.tif',
 'gmted_roughness':'roughness_1KMmn_GMTEDmd.tif',
 'gmted_tpi':'tpi_1KMmn_GMTEDmd.tif',
 'gmted_tri':'tri_1KMmn_GMTEDmd.tif',
 'worldclim_bio':'wc2.1_30s_bio.zip',
 'worldclim_prec':'wc2.1_30s_prec.zip',
 'worldclim_tavg':'wc2.1_30s_tavg.zip',
 'worldclim_tmax':'wc2.1_30s_tmax.zip',
 'worldclim_tmin':'wc2.1_30s_tmin.zip',
 'worldclim_srad':'wc2.1_30s_srad.zip',
 'worldclim_vapr':'wc2.1_30s_vapr.zip',
 'worldclim_wind':'wc2.1_30s_wind.zip',
 'era5ex':'ERA5-EX v4.zip',
 'gisd30':'GISD30_1985-2020_*.rar',
 'grip_density':'GRIP4_density_total.zip',
 'grip_vector':'GRIP4_global_vector_fgdb.zip',
 'ucdb':'GHS_UCDB_GLOBE_R2024A_V1_2.zip',
 'hydro_basin':'BasinATLAS_Data_v10.gdb.zip',
 'hydro_river':'RiverATLAS_Data_v10.gdb.zip',
 'admin0':'geoBoundariesCGAZ_ADM0.zip',
 'admin1':'geoBoundariesCGAZ_ADM1.zip',
 'flood_event':'Global_Flood_Records.gpkg',
}

def inventory(root,out):
    root=Path(root);cee=root/'CEE数据'
    if not cee.exists():raise FileNotFoundError(f'Expected local folder: {cee}')
    files=list(cee.iterdir())
    if len(files)>10_000:raise ValueError('Inventory too broad, examine input folder')
    raw=root/'data'/'raw'
    files.extend(p for p in raw.rglob('*') if p.is_file() and len(p.relative_to(raw).parts)<=5) if raw.exists() else None
    records=[]
    for family,pat in EXPECTED_PATTERNS.items():
        matches=[p for p in files if p.is_file() and p.match(pat)]
        for p in matches:
            record=dict(family=family,path=str(p),size_bytes=p.stat().st_size,
                        status='LOCAL_PRESENT_UNVERIFIED',archive_members=None)
            if p.suffix.lower()=='.zip':
                try:
                    with ZipFile(p) as z:
                        n=z.namelist();record['archive_members']=len(n)
                        record['archive_first_members']=';'.join(n[:5])
                except BadZipFile:
                    record['status']='BAD_ZIP'
            records.append(record)
        if not matches:records.append(dict(family=family,path='',size_bytes=0,
                                            status='NOT_FOUND',archive_members=None))
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(records)
    frame.to_csv(dest,index=False,encoding='utf-8-sig')
    return {'families':len(EXPECTED_PATTERNS),'present_files':int((frame.status=='LOCAL_PRESENT_UNVERIFIED').sum()),
            'missing_families':frame.loc[frame.status=='NOT_FOUND','family'].tolist(),
            'inventory_csv':str(dest)}

def _member_match(items,pattern):
    # Match only TIFF/NC/ASCII originals, never documentation or RAR examples.
    matches=[x for x in items if Path(x).match(pattern) and not x.endswith('/')]
    if not matches:raise FileNotFoundError(f'Archive contains no member matching {pattern}')
    if len(matches)!=1:raise ValueError(f'Expected one archive member, found {len(matches)}: {matches[:10]}')
    return matches[0]

def stage_one(zip_path,glob,out):
    src=Path(zip_path);dest=Path(out)
    if not src.is_file():raise FileNotFoundError(src)
    with ZipFile(src) as z:
        info=z.getinfo(_member_match(z.namelist(),glob))
        if info.file_size>25_000_000_000:
            raise ValueError('Single member >25GB; stage individually with sufficient disk')
        dest.parent.mkdir(parents=True,exist_ok=True)
        proof=dest.with_name(dest.name+'.source.json')
        if dest.is_file() and dest.stat().st_size==info.file_size:
            # The previous version reused based on file length alone. Always
            # calculate CRC-32 against the archive's own member manifest.
            with dest.open('rb') as fp:
                crc=0
                for chunk in iter(lambda:fp.read(8*1024*1024),b''):
                    crc=zlib.crc32(chunk,crc)
            if (crc&0xffffffff)!=info.CRC:
                raise ValueError('Staged TIFF length matches, but original ZIP CRC disagrees: '+str(dest))
            if proof.is_file():
                saved=read_json(proof)
                if saved.get('archive')!=file_identity(src) or saved.get('member_crc32')!=info.CRC:
                    raise ValueError('Staged TIFF belonged to different source version; do not overwrite')
            else:
                json_write(proof,{'archive':file_identity(src),'member':info.filename,
                    'member_size':info.file_size,'member_crc32':info.CRC,
                    'status':'VERIFIED_AGAINST_ZIP_CRC32'})
            return {'status':'REUSED_ZIP_CRC_CHECKED','path':str(dest),'bytes':info.file_size}
        if dest.exists():raise FileExistsError('Incorrect preexisting extracted file: '+str(dest))
        staging=dest.with_name(dest.name+'.writing')
        if staging.exists():raise FileExistsError('Previous interrupted stage: '+str(staging))
        try:
            with z.open(info) as a,staging.open('xb') as b:shutil.copyfileobj(a,b,length=8*1024*1024)
            if staging.stat().st_size!=info.file_size:
                raise IOError('Archive size mismatch')
            os.replace(staging,dest)
            json_write(proof,{'archive':file_identity(src),'member':info.filename,
                'member_size':info.file_size,'member_crc32':info.CRC,
                'status':'VERIFIED_AGAINST_ZIP_CRC32'})
        except Exception:
            if staging.exists():staging.unlink()
            raise
    return {'status':'EXTRACTED_FROM_ZIP_CRC_CHECKED','path':str(dest),'bytes':dest.stat().st_size,'member':info.filename}

def stage_archive(zip_path,out,max_gb=20):
    """Safely extract a selected small source ZIP (e.g. geoBoundaries/GDB/UCDB)."""
    p=Path(zip_path);dest=Path(out)
    if not p.is_file():raise FileNotFoundError(p)
    marker=dest/'archive_extraction_qc.json'
    info={'source':str(p.resolve()),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
    if marker.exists():
        import json
        old=json.loads(marker.read_text(encoding='utf-8'))
        if old.get('source_file')==info and old.get('status')=='OK':
            return {'status':'REUSED_EXTRACTED','out':str(dest),'members':old['members']}
        raise ValueError('Archive contents source changed or unverified; use new versioned directory')
    if dest.exists() and any(dest.iterdir()):raise FileExistsError('Output directory nonempty with no successful extraction QC')
    with ZipFile(p) as z:
        items=[i for i in z.infolist() if not i.is_dir()]
        size=sum(i.file_size for i in items)
        if size>max_gb*1e9:raise ValueError('Archive uncompressed size exceeds declared limit')
        # Prevent path traversal, absolute names and suspicious symlinks.
        for i in items:
            name=i.filename.replace('\\','/')
            parts=Path(name).parts
            if name.startswith('/') or ':' in name or '..' in parts or not parts:
                raise ValueError('Unsafe archive member path: '+name)
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlink in ZIP forbidden: '+name)
        dest.mkdir(parents=True,exist_ok=True)
        for i in items:
            target=dest/i.filename
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as x,target.open('wb') as y:shutil.copyfileobj(x,y,length=8<<20)
        json_write(marker,{'status':'OK','source_file':info,'members':len(items),'uncompressed_bytes':size})
    return {'status':'EXTRACTED_ZIP_CRC_CHECKED','out':str(dest),'members':len(items),'uncompressed_bytes':size}
