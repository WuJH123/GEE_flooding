"""Authenticated bounded download, exact name and immutable content hash.

Production automation requires configured Drive ADC or GCS bucket (GCS may incur
Google Cloud charges). Download is atomic .part -> final after complete response.
"""
from __future__ import annotations
import pathlib,os

def check_auth(mode,bucket=None):
 if mode=='gcs':
  if not bucket:raise ValueError('Bucket required for GCS automated completion')
  from google.cloud import storage
  c=storage.Client();b=c.lookup_bucket(bucket)
  if b is None:raise ValueError('GCS bucket unavailable/permission denied: '+bucket)
  return {'mode':'gcs','bucket':bucket}
 if mode=='drive':
  import google.auth
  scopes=['https://www.googleapis.com/auth/drive.readonly']
  creds,_=google.auth.default(scopes=scopes)
  if not creds.has_scopes(scopes):raise ValueError('Drive ADC lacks drive.readonly scope')
  from googleapiclient.discovery import build
  service=build('drive','v3',credentials=creds,cache_discovery=False)
  service.files().list(pageSize=1,fields='files(id)').execute()
  return {'mode':'drive','drive_adc':True}
 raise ValueError('mode must be drive/gcs')

def _write_bytes(target,content):
 target=pathlib.Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():return target
 tmp=target.with_suffix(target.suffix+'.part')
 with open(tmp,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
 os.replace(tmp,target)
 return target

def get_source(name,out_dir,mode,bucket=None,folder=None,kind="weather"):
 """Only exact names; duplicate Drive names are rejected, not silently replaced."""
 ext='.csv' if kind=='weather' else '.tif'
 p=pathlib.Path(out_dir)/(name+ext)
 if p.exists():return p
 if mode=='gcs':
  from google.cloud import storage
  blob=storage.Client().bucket(bucket).blob('CEE_GF10_GLOBAL_EE_V8_20261106/'+name+ext)
  if not blob.exists():return None
  return _write_bytes(p,blob.download_as_bytes())
 if mode=='drive':
  import google.auth
  from googleapiclient.discovery import build
  scopes=['https://www.googleapis.com/auth/drive.readonly']
  creds,_=google.auth.default(scopes=scopes)
  drive=build('drive','v3',credentials=creds,cache_discovery=False)
  safe=(name+ext).replace("'", "\\'")
  r=drive.files().list(q=f"name = '{safe}' and trashed = false",fields='nextPageToken,files(id,name,mimeType,parents)',pageSize=30).execute()
  found=r.get('files',[])
  if len(found)>1:
   raise ValueError('Ambiguous duplicated Google Drive export names; cannot select unverified result: '+name)
  if not found:return None
  data=drive.files().get_media(fileId=found[0]['id']).execute()
  return _write_bytes(p,data)
 raise ValueError(mode)
