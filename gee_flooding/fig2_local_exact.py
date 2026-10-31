"""Exact local raster -> frozen GF10 zonal statistics, without downloading.

Explicit per-variable manifest and immutable output. Reads *native* pixels,
intersects them with the actual 10km EPSG:6933 polygons. Pixel coverage
fractions are computed by exactextract; do NOT use nearest neighbour class
resampling or pixel-centre counting for publication source totals.

Example manifest:
{"variables":[
 {"name":"hand_m","dataset":"MERIT_HYDRO","epoch":"static",
  "kind":"mean","paths":["E:/.../hnd.tif"],"band":1,"unit":"m"},
 {"name":"population_count_2020","dataset":"GHSL_POP_R2023A","epoch":"2020",
  "kind":"cell_sum","paths":["E:/.../GHS_POP_2020.tif"],"unit":"persons"},
 {"name":"tree_fraction","dataset":"ESA_WORLDCOVER_V200","epoch":"2021",
  "kind":"class_fraction","classes":[10],"paths":["E:/.../WorldCover.tif"],"unit":"fraction"}
]}
Archives and unsupported tile mosaics must be inspected first.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path
import numpy as np
import pandas as pd
from .paths import safe_output,atomic_json

AREA_M2=10000.0**2
SUPPORTED={
    "hand_m":("mean", "MERIT_HYDRO","static"),
    "elevation_m":("mean","MERIT_HYDRO","static"),
    "upstream_area_km2":("mean","MERIT_HYDRO","static"),
    "river_water_fraction":("class_fraction","MERIT_HYDRO","static"),
    "vegetation_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "tree_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "grass_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "wetland_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "water_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "bare_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "cropland_fraction":("class_fraction","ESA_WORLDCOVER_V200","2021"),
    "population_count_2020":("cell_sum","GHSL_POP_R2023A","2020"),
    "built_area_km2_2020":("cell_sum","GHSL_BUILT_S_R2023A","2020"),
    "built_nres_area_km2_2020":("cell_sum","GHSL_BUILT_S_R2023A","2020"),
    "built_fraction_2020":("cell_sum","GHSL_BUILT_S_R2023A","2020"),
    "built_nres_fraction_2020":("cell_sum","GHSL_BUILT_S_R2023A","2020"),
    "built_fraction_2000":("cell_sum","GHSL_BUILT_S_R2023A","2000"),
    "impervious_fraction":("native_fraction","GAIA_OR_GISD_VERSIONED","2020"),
    "built_volume_m3":("cell_sum","GHSL_BUILT_V_VERSIONED","2020"),
}
CLASS_CODES={
    "tree_fraction":[10], "grass_fraction":[30],
    "cropland_fraction":[40],"wetland_fraction":[90,95],
    "water_fraction":[80], "bare_fraction":[60],
    "vegetation_fraction":[10,20,30,40,90,95],
    "river_water_fraction":[1],
}
CELL_SUM_FACTOR={
    "built_area_km2_2020":1/1e6,
    "built_nres_area_km2_2020":1/1e6,
    "built_fraction_2020":1/AREA_M2,
    "built_nres_fraction_2020":1/AREA_M2,
    "built_fraction_2000":1/AREA_M2,
    "population_count_2020":1,
    "built_volume_m3":1
}
FRACTIONS=set(CLASS_CODES)|{"built_fraction_2020","built_nres_fraction_2020",
                              "built_fraction_2000","impervious_fraction"}


def validate_variable(entry):
    name=str(entry.get("name",""))
    if name not in SUPPORTED:
        raise ValueError("Source indicator not in explicit GF10 semantics dictionary: "+name)
    kind,dataset,epoch=SUPPORTED[name]
    for field,expected in [("kind",kind),("dataset",dataset),("epoch",epoch)]:
        if str(entry.get(field))!=expected:
            raise ValueError(name+": "+field+" must be exactly "+expected)
    if kind=="class_fraction":
        codes=entry.get("classes")
        if codes != CLASS_CODES[name]:
            raise ValueError(name+": require exact audited class codes "+str(CLASS_CODES[name]))
    if name in {"built_area_km2_2020","built_nres_area_km2_2020",
                "built_fraction_2020","built_nres_fraction_2020","built_fraction_2000"}:
        if entry.get("native_units")!="m2_per_native_pixel":
            raise ValueError(name+": GHSL BUILT-S must be source m2 per native pixel")
    if name=="population_count_2020" and entry.get("native_units")!="people_per_native_pixel":
        raise ValueError("Population input must be counts per native pixel, not density")
    if name=="built_volume_m3" and entry.get("native_units")!="m3_per_native_pixel":
        raise ValueError("BUILT-V input units unknown; require m3 per source pixel verification")
    paths=entry.get("paths")
    if not isinstance(paths,list) or not 1<=len(paths)<=100:
        raise ValueError(name+": pass 1..100 explicit raster tile paths, not a giant unknown directory")
    if len(set(map(str,paths)))!=len(paths):
        raise ValueError(name+": raster tile paths duplicate")
    if int(entry.get("band",1))<=0:raise ValueError("band must be >=1")
    for p in paths:
        path=Path(p)
        if path.suffix.lower() not in (".tif",".tiff",".vrt",".img"):
            raise ValueError(name+": only inspected raster files; archives require separate review")
        if not path.is_file():raise FileNotFoundError(str(path))


def selected_grid(path,start_row,count):
    if start_row<0 or not 1<=count<=500:
        raise ValueError("Local extraction one batch must have 1..500 GF10 cells")
    grid=pd.read_parquet(path)
    need={"grid_id","grid_x","grid_y"}
    if need-set(grid):raise ValueError("Frozen grid missing GF10 identifiers")
    grid=grid.sort_values("grid_id").iloc[start_row:start_row+count].copy()
    if len(grid)!=count or grid.grid_id.duplicated().any():
        raise ValueError("Declared GF10 slice missing/duplicate")
    grid.grid_id=grid.grid_id.astype(str)
    if any(g!=f"{int(x)}_{int(y)}" for g,x,y in
           zip(grid.grid_id,grid.grid_x,grid.grid_y)):
        raise ValueError("grid_id differs from authoritative EPSG:6933 cell indices")
    return grid


def cell_polys(g):
    import geopandas as gpd
    from shapely.geometry import box
    return gpd.GeoDataFrame(
        {"grid_id":g.grid_id.to_list()},
        geometry=[box(int(x)*10000,int(y)*10000,(int(x)+1)*10000,
                      (int(y)+1)*10000)
                  for x,y in zip(g.grid_x,g.grid_y)],crs="EPSG:6933")


def combine_contributions(parts,grids,name,kind,min_coverage=0.95):
    """Weighted, tile-additive reductions with no duplicate-tile overlap tolerance."""
    g=grids[["grid_id"]].copy()
    agg={str(k):{"count":0.0,"sum":0.0,"class_weight":0.0} for k in g.grid_id}
    if not parts:raise ValueError(name+": no source tiles")
    pixel_area=None
    for item in parts:
        data=item["data"]
        tile_area=float(item["pixel_area"])
        if pixel_area is None:pixel_area=tile_area
        if not np.isclose(pixel_area,tile_area,rtol=.001):
            raise ValueError(name+": mixed pixel resolutions; mosaic to identical native grid first")
        if data.grid_id.duplicated().any():
            raise ValueError(name+": duplicate GF10 ID within one source tile")
        for r in data.itertuples(index=False):
            key=str(r.grid_id)
            if key not in agg:raise ValueError("Tile returned grid not in declared GF10")
            count=float(getattr(r,"count",0) or 0)
            if not np.isfinite(count) or count<0:
                raise ValueError(name+": invalid native pixel coverage")
            if count==0:continue
            entry=agg[key]
            entry["count"]+=count
            if kind=="class_fraction":
                cls=float(getattr(r,"class_share"))
                if not 0<=cls<=1:raise ValueError(name+": invalid categorical share")
                entry["class_weight"]+=count*cls
            elif kind in ("mean","native_fraction"):
                value=float(getattr(r,"mean"))
                if not np.isfinite(value):raise ValueError(name+": nonfinite native mean")
                entry["sum"]+=count*value
            else:
                value=float(getattr(r,"sum"))
                if not np.isfinite(value):raise ValueError(name+": nonfinite native sum")
                entry["sum"]+=value
    rows=[]
    for key,e in agg.items():
        coverage=e["count"]*pixel_area/AREA_M2
        if coverage>1.025:
            raise ValueError(name+": overlapping/duplicated native tiles or incorrect pixel area at "+key)
        missing=coverage<min_coverage
        if e["count"]==0 or missing:
            val=np.nan
        elif kind=="class_fraction":val=e["class_weight"]/e["count"]
        elif kind in ("mean","native_fraction"):val=e["sum"]/e["count"]
        else:val=e["sum"]*CELL_SUM_FACTOR[name]
        if np.isfinite(val) and name in FRACTIONS and not -1e-5<=val<=1.00001:
            raise ValueError(name+": fraction outside [0,1]: "+str(val))
        if np.isfinite(val) and name in ("population_count_2020","built_area_km2_2020",
                                         "built_nres_area_km2_2020","upstream_area_km2",
                                         "built_volume_m3") and val<0:
            raise ValueError(name+": physically negative value")
        rows.append(dict(grid_id=key,**{name:val},
                         **{f"coverage_{name}":min(coverage,1.0)}))
    return pd.DataFrame(rows)


def extract(root,grid_path,manifest,tag="fig2_local_exact_v1",
            start_row=0,count=20,min_coverage=.95,backend="exactextract"):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Output tag must be fig2_* without separators")
    if not .5<=min_coverage<=1:raise ValueError("Expected 0.5<=min coverage<=1")
    manifest=Path(manifest)
    config=json.loads(manifest.read_text(encoding="utf-8-sig"))
    variables=config.get("variables")
    if not isinstance(variables,list) or not variables:
        raise ValueError("Manifest must contain variables list")
    if len(set(i.get("name") for i in variables))!=len(variables):
        raise ValueError("Duplicate indicator declarations")
    for item in variables:validate_variable(item)
    if backend not in ("exactextract","shapely"):
        raise ValueError("Only audited exactextract or shapely backends are supported")
    if backend=="exactextract":
        try:
            from exactextract import exact_extract
            from exactextract.raster import RasterioRasterSource
        except ImportError as exc:
            raise RuntimeError('Install exactextract or use --backend shapely for audited equal-area source TIFFs') from exc
    else:
        from .fig2_shapely_fallback import extract_source
    import rasterio
    gf=selected_grid(grid_path,start_row,count)
    polygons=cell_polys(gf)
    output=gf[["grid_id"]].copy()
    details=[]
    for spec in variables:
        name=spec["name"]
        kind=spec["kind"]
        parts=[]
        for file in spec["paths"]:
            with rasterio.open(file) as src:
                if src.crs is None or not src.crs.is_projected:
                    raise ValueError(name+": raster must be in metric projected CRS; reproject locally to suitable equal-area CRS and audit before extracting "+str(file))
                from pyproj import CRS
                axis_info=CRS.from_user_input(src.crs).axis_info
                if axis_info and any(x.unit_name.lower() not in ("metre","meter") for x in axis_info):
                    raise ValueError(name+": native raster CRS not in meters")
                if src.transform.b!=0 or src.transform.d!=0:
                    raise ValueError(name+": rotated raster requires audited orthogonal reprojection")
                pixel_area=abs(src.transform.a*src.transform.e)
                if not 1<=pixel_area<=100_000_000:
                    raise ValueError(name+": implausible native pixel area")
                band=int(spec.get("band",1))
                if band>src.count:raise ValueError(name+": band exceeds raster count")
                zones=polygons.to_crs(src.crs)
                if backend=="shapely":
                    frame=extract_source(src,gf,band,kind,spec.get("classes",[]))
                else:
                    raster=RasterioRasterSource(src,band_idx=band,name=name)
                    ops=["count","sum","mean"]
                    if kind=="class_fraction":ops+=["unique","frac"]
                    frame=exact_extract(raster,zones,ops,include_cols=["grid_id"],
                                        output="pandas",max_cells_in_memory=5_000_000)
                    if "grid_id" not in frame or "count" not in frame:
                        raise ValueError(name+": exactextract returned unexpected schema")
                    if kind=="class_fraction":
                        if not {"unique","frac"}.issubset(frame):
                            raise ValueError("exactextract requires unique and frac arrays")
                        classes=set(spec["classes"])
                        def class_share(r):
                            unique=np.atleast_1d(r["unique"])
                            fraction=np.atleast_1d(r["frac"])
                            if len(unique)!=len(fraction):
                                raise ValueError("Categorical arrays have mismatched lengths")
                            return float(sum(float(v) for k,v in zip(unique,fraction)
                                             if not pd.isna(k) and int(k) in classes))
                        frame["class_share"]=frame.apply(class_share,axis=1)
                parts.append({"data":frame,"pixel_area":pixel_area})
                details.append(dict(name=name,path=str(file),crs=str(src.crs),
                                    band=band,pixel_area_m2=pixel_area,
                                    raster_bytes=Path(file).stat().st_size,
                                    data_year=spec["epoch"],data_source=spec["dataset"]))
        result=combine_contributions(parts,gf,name,kind,min_coverage)
        output=output.merge(result,on="grid_id",how="left",validate="one_to_one")
    # Detect inconsistent GHSL total vs NRES if both are measured in same grid.
    if {"built_area_km2_2020","built_nres_area_km2_2020"}<=set(output):
        a=output.built_area_km2_2020
        b=output.built_nres_area_km2_2020
        if (b>a+0.01).fillna(False).any():
            raise ValueError("GHSL NRES built area exceeds total built area")
    result_dir=safe_output(root,"data/derived/"+tag)
    if result_dir.exists():raise FileExistsError("Refusing to overwrite "+str(result_dir))
    result_dir.mkdir(parents=True,exist_ok=False)
    output.to_parquet(result_dir/"fig2_local_GF10_indicators.parquet",index=False)
    cover={spec["name"]:{"valid_n":int(output[spec["name"]].notna().sum()),
          "coverage_mean":float(output[f'coverage_{spec["name"]}'].mean()),
          "missing_cells":int(output[spec["name"]].isna().sum())} for spec in variables}
    qc={"status":"LOCAL_EXACT_GF10_PARTIAL" if any(v["missing_cells"] for v in cover.values())
       else "LOCAL_EXACT_GF10_SCOPE_COMPLETE_NEEDS_SOURCE_AUDIT",
       "grid_cell_count":len(gf),"grid_crs":"EPSG:6933","cell_area_m2":AREA_M2,
       "method":backend+"_native_pixel_fraction_weighted",
       "min_pixel_coverage":min_coverage,"indicator_coverage":cover,
       "raster_metadata":details,"physical_validation":False,
       "full_global_coverage":False,
       "caveat":"Source year, license, raster semantics and full-region overlap require audit; no GEE exports made"}
    atomic_json(result_dir/"fig2_local_exact_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--tag",default="fig2_local_exact_v1")
    p.add_argument("--start-row",type=int,default=0)
    p.add_argument("--count",type=int,default=20)
    p.add_argument("--min-coverage",type=float,default=.95)
    p.add_argument("--backend",choices=["exactextract","shapely"],default="exactextract")
    a=p.parse_args(argv)
    print(json.dumps(extract(a.root,a.grid,a.manifest,a.tag,
                             a.start_row,a.count,a.min_coverage,a.backend),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
