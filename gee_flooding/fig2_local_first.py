"""Figure 2 LOCAL-FIRST source triage for the user's 240k-file inventory.

No file deletion, unpacking, raster processing, network calls or Earth Engine
submission. The inventory CSV is a CANDIDATE INDEX, not proof of usable coverage.
Every candidate needs an explicit metadata, band, epoch and license contract
before being admitted to a frozen GF10 indicator table.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
import rasterio
from .paths import safe_output, atomic_json

# Conservative source-family patterns; longer targeted terms distinguish files
# such as GHS-BUILT-V volume from BUILT-S area, and MERIT from other DEMs.
FAMILIES = {
 "ghsl_built_s_2020": (r"ghs[_ -]?built[_ -]?s|ghs[_ -]?buS|建成面", r"2020|E2020", "exposure", "JRC/GHSL/P2023A/GHS_BUILT_S/2020"),
 "ghsl_built_s_2000": (r"ghs[_ -]?built[_ -]?s|ghs[_ -]?buS|建成面", r"2000|E2000", "exposure", "JRC/GHSL/P2023A/GHS_BUILT_S/2000"),
 "ghsl_built_v": (r"built[_ -]?v|BUILT-V|建筑体积", r"2020|E2020", "exposure", "JRC/GHSL/P2023A/GHS_BUILT_V/2020"),
 "ghsl_pop_2020": (r"ghs[_ -]?pop|GHS_POP|Worldpop|人口格网", r"2020", "exposure", "JRC/GHSL/P2023A/GHS_POP/2020"),
 "merit_hand": (r"MERIT|HAND|相对高程", r".", "sensitivity", "MERIT/Hydro/v1_0_1"),
 "merit_upa": (r"MERIT|HydroATLAS|汇流面积", r".", "sensitivity", "MERIT/Hydro/v1_0_1"),
 "dem_elevation": (r"DEM|高程|elv", r".", "sensitivity", "MERIT/Hydro/v1_0_1"),
 "gaia_impervious_2020": (r"GAIA|GISD30|不透水", r"2020|2019", "sensitivity", "GEE / local version-verified"),
 "landcover_2021": (r"WorldCover|ESA[_ -]?WC|2021.*土地覆盖", r"2021|v200", "adaptation_proxy", "ESA/WorldCover/v200"),
 "landcover_2020": (r"土地利用|land.?cover|land.?use|EULUC", r"2020", "adaptation_proxy", "ESA/WorldCover/v200 (not same class legend)"),
 "roads": (r"GRIP|道路|HydroRIVERS", r".", "adaptation_proxy", "Local spatial vector processing"),
 "nightlights": (r"night.?light|夜间灯光|灯光指数", r"2022|2020", "reporting_selection", "Local data source"),
 "ibtracs": (r"IBTrACS", r".", "storm_track_subset", "NOAA/IBTrACS"),
 "independent_physical_candidates": (r"CN.?Floods|河南.*内涝|伦敦.*地表水|水深|水位", r".", "physical_validation_candidate", "Manual event-specific review"),
}
PATH_COLUMNS = ("path", "full_path", "file_path", "absolute_path", "filepath",
                "file", "路径", "完整路径", "文件路径")
RASTER_EXT = {".tif", ".tiff", ".vrt", ".img"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}
SMALL_DOWNLOAD_BYTES = 10 * 1024**3


def load_inventory(index):
    for enc in ("utf-8-sig", "gb18030"):
        try:
            tab=pd.read_csv(index,encoding=enc,low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Unable to decode input CSV")
    cols={str(k).strip().lower():k for k in tab.columns}
    field=next((cols[k] for k in PATH_COLUMNS if k in cols),None)
    if field is None:
        raise ValueError("Inventory CSV needs a full path field, available: "+", ".join(map(str,tab.columns)))
    paths=tab[field].dropna().astype(str).str.strip()
    # Some inventories have directory and filename in separate columns.
    if not paths.str.contains(r"[/\\]").any():
        raise ValueError("Path column contains filenames only; need absolute paths")
    return paths.drop_duplicates().tolist(), len(tab), str(field)


def classify(rawpath):
    s=str(rawpath).replace("\\","/").lower()
    filename=Path(s).name
    ext=Path(filename).suffix.lower()
    matched=[]
    for key,(pattern,epoch,pillar,fallback) in FAMILIES.items():
        if re.search(pattern,s,re.I) and re.search(epoch,s,re.I):
            if ext in RASTER_EXT or ext in ARCHIVE_EXT or ext in {".gpkg",".shp",".parquet",".csv",".xlsx",".nc"}:
                matched.append(key)
    return matched


def probe_raster(path):
    with rasterio.open(path) as ds:
        crs=ds.crs
        info=dict(crs=str(crs) if crs else None,
                  bands=ds.count, pixel_width=float(abs(ds.transform.a)),
                  pixel_height=float(abs(ds.transform.e)),
                  nodata=None if ds.nodata is None else float(ds.nodata),
                  bounds=[float(v) for v in ds.bounds],
                  dtype=ds.dtypes[0] if ds.count else None)
        info["crs_ok"]=bool(crs)
        info["affine_ok"]=bool(ds.transform.is_rectilinear and ds.transform.a!=0 and ds.transform.e!=0)
        info["transform_is_geographic"]=bool(crs and crs.is_geographic)
        return info


def triage(index,root,tag="fig2_local_candidates_v1",max_per_family=100):
    if not re.fullmatch(r"fig2_[A-Za-z0-9_-]+",tag):
        raise ValueError("Use immutable fig2_* result tag")
    if not 1<=max_per_family<=2000:raise ValueError("max_per_family must be 1..2000")
    paths,total,column=load_inventory(index)
    selected={key:[] for key in FAMILIES}
    # Never inspect all 240k raster contents. Filter filenames first.
    for raw in paths:
        for key in classify(raw):
            if len(selected[key])<max_per_family:
                selected[key].append(raw)
    rows=[]
    for key, candidates in selected.items():
        _,_,pillar,fallback=FAMILIES[key]
        for raw in candidates:
            p=Path(raw)
            ext=p.suffix.lower()
            row=dict(family=key,pillar=pillar,path=str(p),
                     exists=p.is_file(),format=ext,bytes=p.stat().st_size if p.is_file() else None,
                     gee_fallback=fallback,metadata_checked=False,
                     recommended_action="VERIFY_SOURCE_YEAR_BAND_UNITS",
                     pixel_size_m_verified=False)
            if ext in ARCHIVE_EXT:
                row["recommended_action"]="ARCHIVE_INSPECT_CONTENTS_NO_EXTRACTION"
            elif ext in RASTER_EXT and p.is_file():
                try:
                    metadata=probe_raster(p)
                    row.update(metadata)
                    row["metadata_checked"]=True
                    row["recommended_action"]=("LOCAL_RASTER_VERIFY_EPOCH_AND_BAND"
                         if metadata["crs_ok"] and metadata["affine_ok"]
                         else "REJECT_MISSING_CRS_OR_TRANSFORM")
                except Exception as exc:
                    row["error"]=str(exc)[:250]
                    row["recommended_action"]="REJECT_RASTER_OPEN_FAILED"
            elif ext in RASTER_EXT:
                row["recommended_action"]="FILE_NOT_PRESENT_ON_THIS_MACHINE"
            else:
                row["recommended_action"]="REVIEW_TABULAR_OR_VECTOR_NOT_READY_FOR_RASTER_GEE"
            rows.append(row)
    out=safe_output(root,"reports/"+tag)
    if out.exists():raise FileExistsError("Refusing to overwrite "+str(out))
    out.mkdir(parents=True,exist_ok=False)
    data=pd.DataFrame(rows)
    data.to_csv(out/"fig2_local_candidates.csv",index=False,encoding="utf-8-sig")
    summary=[]
    for key,(_,_,pillar,fallback) in FAMILIES.items():
        part=data[data.family.eq(key)] if len(data) else pd.DataFrame()
        validated=(part.recommended_action.eq("LOCAL_RASTER_VERIFY_EPOCH_AND_BAND").sum()
                   if len(part) else 0)
        summary.append(dict(source_family=key,pillar=pillar,
                            candidate_files=int(len(part)),crs_valid_files=int(validated),
                            decision=("LOCAL_PROBE_FIRST" if validated
                                      else "GEE_OR_SOURCE_METADATA_NEEDED"),
                            gee_fallback=fallback))
    pd.DataFrame(summary).to_csv(out/"fig2_family_gaps.csv",index=False,encoding="utf-8-sig")
    qc={"status":"LOCAL_READONLY_CANDIDATES_NOT_GLOBAL_COMPLETENESS",
        "inventory_csv":str(index),"input_rows":int(total),
        "unique_paths":len(paths),"path_column":column,
        "matched_candidates":len(rows),"families":len(FAMILIES),
        "source_raster_values_read":False,"GEE_tasks_submitted":False,
        "automatic_downloads":0,"local_files_modified":0,
        "publication_ready":False,
        "new_download_limit_bytes":SMALL_DOWNLOAD_BYTES,
        "warning":"CRS validity does not verify raster version, value semantics, actual spatial coverage or licensing"}
    atomic_json(out/"fig2_local_first_qc.json",qc)
    return qc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index",type=Path,required=True,help="Codex dataset_inventory_20261031.csv")
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--tag",default="fig2_local_candidates_v1")
    p.add_argument("--max-per-family",type=int,default=100)
    a=p.parse_args(argv)
    print(json.dumps(triage(a.index,a.root,a.tag,a.max_per_family),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":main()
