"""M03 local-first: extract regular 0.1° CF NetCDF source to frozen GF10.

One input file can contain one or several UTC days. Read only selected
lat/lon pixels, using their projected overlap area with each original 10km
EPSG:6933 polygon; never use nearest-neighbour or pretend 0.1° == GF10.
Use NASA daily Final variables precipitation [mm/day], precipitation_cnt
[0..48]. Other variables must specify their audited original units.
No GEE submission and no automatic downloads.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box,Polygon
from shapely.ops import transform
from .paths import safe_output,atomic_json

def _edges(v):
    v=np.asarray(v,float)
    if v.ndim!=1 or len(v)<2 or not np.isfinite(v).all():
        raise ValueError("Require 1-D regular latitude/longitude coordinate")
    d=np.diff(v)
    if not (np.all(d>0) or np.all(d<0)):
        raise ValueError("Coordinate must be strictly monotonic")
    if not np.allclose(d,d[0],rtol=.01):
        raise ValueError("Irregular native cells require a separate audited conservative regrid")
    step=float(d[0])
    return np.concatenate(([v[0]-step/2],(v[:-1]+v[1:])/2,[v[-1]+step/2]))

def _grid_weights(g,lat,lon):
    # Bounded by a small region subset; source native NetCDF must have regular lat/lon.
    lat_edges=_edges(lat);lon_edges=_edges(lon)
    if np.any(abs(lat_edges)>90+1e-4):
        raise ValueError("Invalid latitude cell bounds")
    if np.any(abs(lon_edges)>180+1e-4):
        raise ValueError("Antimeridian or 0-360 longitudes require a separately checked source subset")
    proj=Transformer.from_crs("EPSG:4326","EPSG:6933",always_xy=True)
    latlo=np.minimum(lat_edges[:-1],lat_edges[1:])
    lathi=np.maximum(lat_edges[:-1],lat_edges[1:])
    lonlo=np.minimum(lon_edges[:-1],lon_edges[1:])
    lonhi=np.maximum(lon_edges[:-1],lon_edges[1:])
    rows=[]
    for row in g.itertuples(index=False):
        target=box(row.grid_x*10000,row.grid_y*10000,
                   (row.grid_x+1)*10000,(row.grid_y+1)*10000)
        inv=Transformer.from_crs("EPSG:6933","EPSG:4326",always_xy=True)
        # densified polygon edge determines conservative candidate cell bounds
        ring=[]
        corners=list(target.exterior.coords)
        for a,b in zip(corners[:-1],corners[1:]):
            for k in range(16):
                t=k/16
                ring.append(inv.transform(a[0]*(1-t)+b[0]*t,
                                          a[1]*(1-t)+b[1]*t))
        coords=np.array(ring)
        if np.ptp(coords[:,0])>180:raise ValueError("Antimeridian GF10 cell not supported")
        indices_lat=np.flatnonzero((lathi>coords[:,1].min())&(latlo<coords[:,1].max()))
        indices_lon=np.flatnonzero((lonhi>coords[:,0].min())&(lonlo<coords[:,0].max()))
        vals=[]
        for il in indices_lat:
            for io in indices_lon:
                l0,l1=float(lonlo[io]),float(lonhi[io])
                a0,a1=float(latlo[il]),float(lathi[il])
                # four edges sampled to represent lat/lon curvature in equal area
                ring2=[]
                for aa,bb in zip([(l0,a0),(l1,a0),(l1,a1),(l0,a1)],
                                 [(l1,a0),(l1,a1),(l0,a1),(l0,a0)]):
                    for k in range(4):
                        t=k/4
                        ring2.append(proj.transform(aa[0]*(1-t)+bb[0]*t,
                                                    aa[1]*(1-t)+bb[1]*t))
                part=target.intersection(Polygon(ring2)).area
                if part>0:vals.append((int(il),int(io),part))
        total=sum(w for _,_,w in vals)
        if total<.95*10000**2:
            raise ValueError(f"Insufficient CF native source coverage for GF10 {row.grid_id}: {total/1e8:.3f}")
        if total>1.025*10000**2:
            raise ValueError("Source native cells overlap in GF10 area")
        rows.append((str(row.grid_id),vals))
    return rows


def extract(root,grid,files,variables,tag):
    if not re.fullmatch(r"fig2_[a-zA-Z0-9_-]+",tag):
        raise ValueError("Use unique fig2_* output version")
    try:
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError('Install climate extras: pip install ".[climate]"') from exc
    g=pd.read_parquet(grid)
    if not {"grid_id","grid_x","grid_y"}<=set(g):raise ValueError("Original GF10 grid required")
    if g.grid_id.duplicated().any() or len(g)>500:
        raise ValueError("Use <=500 GF10 cells per local NetCDF region batch")
    files=[Path(x) for x in files]
    if not files or len(files)>400 or any(not x.is_file() for x in files):
        raise ValueError("Provide 1..400 existing NetCDF files; no downloading")
    pairs=dict(k.split(":",1) for k in variables.split(","))
    if not pairs or len(pairs)>6 or any(not v or not k for k,v in pairs.items()):
        raise ValueError("Explicit source-variable:output-variable mapping required")
    if any(v not in {"rain_d_mm","precipitation_cnt","rain_3h_mm",
                     "soil_water_0_7cm","soil_water_7_28cm","temperature_2m_k"}
           for v in pairs.values()):
        raise ValueError("Only approved Figure2 variables")
    rows=[];cached={}
    for file in files:
        with xr.open_dataset(file,decode_times=True) as ds:
            lat_name=next((k for k in ("lat","latitude") if k in ds.coords),None)
            lon_name=next((k for k in ("lon","longitude") if k in ds.coords),None)
            time_name=next((k for k in ("time","valid_time") if k in ds.coords),None)
            if not lat_name or not lon_name or not time_name:
                raise ValueError(f"CF coordinates missing in {file}")
            lat=ds[lat_name].to_numpy();lon=ds[lon_name].to_numpy()
            # Only subsets with at most 5e6 native grid cells, no hidden global 3h caching
            if len(lat)*len(lon)>5_000_000:
                raise ValueError("Subset NASA/CDS NetCDF by study region first")
            signature=(len(lat),len(lon),float(lat[0]),float(lat[-1]),
                       float(lon[0]),float(lon[-1]))
            if signature not in cached:
                cached[signature]=_grid_weights(g,lat,lon)
            weights=cached[signature]
            for original,target in pairs.items():
                if original not in ds:raise ValueError(f"Missing {original} in {file}")
                data=ds[original]
                dims=set(data.dims)
                if dims!={time_name,lat_name,lon_name}:
                    raise ValueError(f"Unexpected extra dimensions {data.dims} in {original}")
                # Essential unit audit for primary NASA daily, no 24x/0.5x duplication
                if target=="rain_d_mm" and data.attrs.get("units") not in ("mm/day","mm d-1","mm"):
                    raise ValueError("Daily NASA precipitation source units must be mm/day")
            days=pd.to_datetime(ds[time_name].values,utc=True).tz_localize(None).normalize()
            if pd.Index(days).has_duplicates:raise ValueError("Duplicate NetCDF UTC days")
            for t,day in enumerate(days):
                # Only selected native pixel slices, not full global raster
                values={}
                for source,alias in pairs.items():
                    values[alias]=ds[source].isel({time_name:t}).transpose(
                        lat_name,lon_name)
                for gid,items in weights:
                    row={"grid_id":gid,"date":day}
                    il=[p[0] for p in items];io=[p[1] for p in items]
                    areas=np.asarray([p[2] for p in items],float)
                    for alias,da in values.items():
                        # Pairwise indexed small bounding region, not full image .values
                        arr=da.isel({lat_name:xr.DataArray(il,dims=["point"]),
                                     lon_name:xr.DataArray(io,dims=["point"])}).values
                        arr=np.asarray(arr,float)
                        if not np.isfinite(arr).all():
                            row[alias]=np.nan
                        else:
                            row[alias]=float(np.dot(arr,areas)/areas.sum())
                    rows.append(row)
    data=pd.DataFrame(rows)
    # Several different source variables from same file share row IDs:
    # group by grid/date preserving each source field, BUT independent files
    # may not overlap same variable/day with inconsistent data.
    if data.duplicated(["grid_id","date"]).any():
        # This module takes one source family at a time. Repeated time
        # or overlapping files are rejected rather than silently averaging.
        raise ValueError("Duplicate GF10×UTC day across NetCDF files: split sources, drop overlap")
    if data.empty:raise ValueError("No CF days found")
    output=safe_output(root,"data/derived/"+tag)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True,exist_ok=False)
    data.sort_values(["grid_id","date"]).to_parquet(output/"fig2_CF_daily_GF10.parquet",index=False)
    atomic_json(output/"fig2_CF_daily_QC.json",{
        "status":"LOCAL_CF_AREA_WEIGHTED_NEEDS_TEMPORAL_COVERAGE_QC",
        "source_files":[str(x) for x in files],"source_variables":pairs,
        "n_rows":len(data),"n_GF10":data.grid_id.nunique(),
        "min_date":str(data.date.min().date()),"max_date":str(data.date.max().date()),
        "grid_crs":"EPSG:6933","no_GEE_jobs":True,
        "limitation":"Original 0.1-degree meteorology is not 10km measured resolution; source units and time basis require final audit"})
    return data


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--input-dir",type=Path,required=True)
    p.add_argument("--glob",default="*.nc4")
    p.add_argument("--variables",required=True,help="example precipitation:rain_d_mm,precipitation_cnt:precipitation_cnt")
    p.add_argument("--tag",default="fig2_imerg_daily_region_v1")
    a=p.parse_args(argv)
    files=sorted(a.input_dir.glob(a.glob))
    result=extract(a.root,a.grid,files,a.variables,a.tag)
    print(json.dumps({"n_rows":len(result),"n_grids":result.grid_id.nunique()},
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()
