"""Source-identical EE expressions and bounded Drive/GCS exports.

No calls in this module initiate jobs unless explicit submit() is invoked.
Preserve source 10km equal-area identity for MERIT; meteorology is ~11km native.
"""
from __future__ import annotations
import pathlib,sys
from . import core

def initialize():
 import ee
 ee.Initialize(project=core.PROJECT)
 return ee

def model_from_local(root):
 v3=core.root_files(root)['v3']
 if not (v3/'ceeprodgee'/'ee_model.py').is_file():raise FileNotFoundError('Validated V3 code not present: '+str(v3))
 sys.path.insert(0,str(v3))
 from ceeprodgee import ee_model
 if ee_model.TRANSFORM_10!=[10000,0,0,0,-10000,0]:raise ValueError('Upstream source 10km affine changed')
 return ee_model

def spatial_limits():
 from pyproj import Transformer
 tr=Transformer.from_crs(4326,6933,always_xy=True)
 return sorted((tr.transform(-180,0)[0],tr.transform(180,0)[0]))

def projected_seam_segments(x,y):
    """Periodic x representation of one original EPSG6933 10km cell.

    This applies ONLY to sampled coarse meteorology; MERIT source hydrology
    still needs independent native-pixel science verification for seam 450.
    """
    lo,hi=spatial_limits();width=hi-lo
    a=x*10000.;length=10000.
    start=(a-lo)%width+lo
    end=start+length
    yy=y*10000.;top=(y+1)*10000.
    if end<=hi:
        return [[start,yy,end,top]]
    return [[start,yy,hi,top],[lo,yy,lo+(end-hi),top]]


def rect(ee,x,y,proj):
    segments=projected_seam_segments(x,y)
    if len(segments)==1:
        return ee.Geometry.Rectangle(segments[0],proj=proj,geodesic=False)
    # A bounded two-polygon periodic window, never a 360-degree raster warp.
    rings=[]
    for xa,ya,xb,yb in segments:
        rings.append([[[xa,ya],[xb,ya],[xb,yb],[xa,yb],[xa,ya]]])
    return ee.Geometry.MultiPolygon(rings,proj=proj,geodesic=False)


def build_weather(ee,root,rows,wkt):
 model=model_from_local(root)
 features=[]
 for z in rows.itertuples(index=False):
  features.append(ee.Feature(rect(ee,int(z.grid_x),int(z.grid_y),wkt),
    {'grid_id':str(z.grid_id),'date_utc':str(z.date_utc)}))
 if len(features)>600:raise ValueError('Weather task too many polygons')
 all_parts=[]
 for d in sorted(set(rows.date_utc)):
  # Every date uses the original isolated-v3 43-window 3h + 30d antecedent graph.
  f=ee.FeatureCollection([a for a,z in zip(features,rows.itertuples(index=False)) if z.date_utc==d])
  res=model.event_image(ee,str(d)).reduceRegions(collection=f,reducer=ee.Reducer.mean(),
    crs='EPSG:4326',scale=11132,tileScale=4)
  all_parts.append(res)
 if len(all_parts)>8:raise ValueError('Maximum 8 meteorological dates per task')
 return ee.FeatureCollection(all_parts).flatten()

def build_merit(ee,root,row,wkt):
 model=model_from_local(root)
 x,y=int(row.crop_x0),int(row.crop_y0);w,h=int(row.width),int(row.height)
 if not(1<=w<=10 and 1<=h<=10):raise ValueError('MERIT not an accepted <=10x10 compact block')
 left,right=spatial_limits()
 bbox=[x*10000,y*10000,(x+w)*10000,(y+h)*10000]
 if bbox[0]<left+1 or bbox[2]>right-1:raise ValueError('SEAM_MERIT_BLOCK_NOT_SCIENTIFICALLY_EQUIVALENT')
 calc=[max(bbox[0]-80000,left+1),bbox[1]-80000,min(bbox[2]+80000,right-1),bbox[3]+80000]
 center=[bbox[0]+4999,bbox[1]+4999,bbox[2]-4999,bbox[3]-4999]
 if not calc[0]<calc[2] or not center[0]<center[2]:raise ValueError('Illegal MERIT output ROI')
 roi=ee.Geometry.Rectangle(calc,proj=wkt,geodesic=False)
 exp=ee.Geometry.Rectangle(center,proj=wkt,geodesic=False)
 image=model.merit(ee,roi,wkt).unmask(-9999)
 return image,exp,bbox

def export(ee,kind,source,name,mode='drive',bucket=None,folder=None,wkt=None,region=None):
 if not name.startswith(core.RUN):raise ValueError('Export description not v8 namespace')
 if mode=='gcs':
  if not bucket:raise ValueError('No GCS bucket configured; refuse unattended export')
  if kind=='weather':
   return ee.batch.Export.table.toCloudStorage(collection=source,description=name,bucket=bucket,
    fileNamePrefix=core.RUN+'/'+name,fileFormat='CSV',selectors=core.FIELDS)
  return ee.batch.Export.image.toCloudStorage(image=source,description=name,bucket=bucket,
    fileNamePrefix=core.RUN+'/'+name,region=region,crs=wkt,crsTransform=[10000,0,0,0,-10000,0],
    maxPixels=300,fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
 if mode=='drive':
  if kind=='weather':return ee.batch.Export.table.toDrive(collection=source,description=name,
      folder=folder or core.RUN,fileNamePrefix=name,fileFormat='CSV',selectors=core.FIELDS)
  return ee.batch.Export.image.toDrive(image=source,description=name,
    folder=folder or core.RUN,fileNamePrefix=name,region=region,crs=wkt,
    crsTransform=[10000,0,0,0,-10000,0],maxPixels=300,fileFormat='GeoTIFF',
    formatOptions={'cloudOptimized':True,'noData':-9999})
 raise ValueError('Use drive or gcs')

def task_status(ee,rec):
 if not rec['operation']:return ('INTENT',None,'No confirmed EE operation; reconcile manually')
 op=ee.data.getOperation(rec['operation']);m=op.get('metadata') or {}
 sec=m.get('batchEecuUsageSeconds',m.get('batch_eecu_usage_seconds'))
 return m.get('state','UNKNOWN'),float(sec)/3600 if sec is not None else None,(op.get('error') or {}).get('message')
