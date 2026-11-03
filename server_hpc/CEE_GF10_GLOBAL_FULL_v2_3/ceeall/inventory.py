"""Inventory, data-preserving archive metadata inspection."""
from __future__ import annotations
from pathlib import Path
import zipfile
from .common import atomic_json

def family(name):
    name=name.lower()
    if name.startswith('wc2.1_'):return 'worldclim'
    if name.startswith('era5-ex'):return 'era5ex'
    if name.startswith(('elevation_','slope_','roughness_','tpi_','tri_')):return 'gmted'
    if name.startswith('gisd30_'):return 'gisd30'
    if name.startswith('basinatlas'):return 'basinatlas'
    if name.startswith('riveratlas'):return 'riveratlas'
    if name.startswith('grip4_density'):return 'grip_density'
    if name.startswith('grip4_global'):return 'grip_vector'
    if name.startswith('geoboundariescgaz_adm'):return 'admin'
    if name.startswith('ghs_ucdb'):return 'ucdb'
    if name.startswith('global_flood_records'):return 'flood_records'
    return 'unmapped'

def inventory(src,out):
    import pandas as pd
    src=Path(src);out=Path(out)
    if not src.is_dir():raise FileNotFoundError(src)
    rows=[]
    for p in sorted(src.iterdir()):
        if not p.is_file():continue
        row={'filename':p.name,'path':str(p),'family':family(p.name),'bytes':p.stat().st_size,
             'format':p.suffix.lower(),'archive_members':None,'decompressed_bytes':None,'problem':None}
        if p.suffix.lower()=='.zip':
            try:
                with zipfile.ZipFile(p) as z:
                    row['archive_members']=len(z.infolist())
                    row['decompressed_bytes']=sum(x.file_size for x in z.infolist() if not x.is_dir())
                    names=[x.filename.replace('\\','/') for x in z.infolist()]
                    if any(x.startswith('/') or '..' in Path(x).parts for x in names):row['problem']='ZIP_PATH_TRAVERSAL'
            except Exception as e:row['problem']='UNREADABLE_ZIP '+str(e)
        rows.append(row)
    if not rows:raise ValueError('Empty input inventory '+str(src))
    df=pd.DataFrame(rows);out.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(out,index=False,encoding='utf-8-sig')
    atomic_json(out.with_suffix('.json'),{'status':'INVENTORY_ONLY_NO_DATA_PROCESSING',
       'files':len(df),'total_bytes':int(df.bytes.sum()),
       'families':df.groupby('family').size().to_dict(),
       'errors':df.loc[df.problem.notna(),['filename','problem']].to_dict('records'),
       'no_original_data_modified':True})
    return {'file_count':len(df),'output':str(out),'families':df.groupby('family').size().to_dict()}
