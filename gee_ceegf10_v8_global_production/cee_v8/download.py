"""Authenticated bounded download, exact name and immutable content hash.

Drive downloads reuse the registered Earth Engine OAuth credential and the
independent project as quota project. GCS requires an existing authorized bucket.
Download is atomic .part -> final after a complete response.
"""
from __future__ import annotations
import pathlib,os
from . import core

def _drive_session():
 import ee
 from google.auth.transport.requests import AuthorizedSession
 return AuthorizedSession(ee.data.get_persistent_credentials().with_quota_project(core.PROJECT))

def check_auth(mode,bucket=None):
 if mode=='gcs':
  if not bucket:raise ValueError('Bucket required for GCS automated completion')
  from google.cloud import storage
  c=storage.Client();b=c.lookup_bucket(bucket)
  if b is None:raise ValueError('GCS bucket unavailable/permission denied: '+bucket)
  return {'mode':'gcs','bucket':bucket}
 if mode=='drive':
  response=_drive_session().get('https://www.googleapis.com/drive/v3/files',
       params={'pageSize':1,'fields':'files(id)'},timeout=60)
  response.raise_for_status()
  return {'mode':'drive','credential_source':'earthengine_persistent'}
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
  drive=_drive_session()
  safe=(name+ext).replace("'", "\\'")
  response=drive.get('https://www.googleapis.com/drive/v3/files',params={
      'q':f"name = '{safe}' and trashed = false",
      'fields':'nextPageToken,files(id,name,mimeType,parents)',
      'pageSize':30},timeout=60)
  response.raise_for_status()
  r=response.json();found=r.get('files',[])
  if r.get('nextPageToken'):
   raise ValueError('More than one page of same-named Drive exports: '+name)
  if len(found)>1:
   raise ValueError('Ambiguous duplicated Google Drive export names; cannot select unverified result: '+name)
  if not found:return None
  response=drive.get(f"https://www.googleapis.com/drive/v3/files/{found[0]['id']}",
                     params={'alt':'media'},timeout=120)
  response.raise_for_status()
  return _write_bytes(p,response.content)
 raise ValueError(mode)
