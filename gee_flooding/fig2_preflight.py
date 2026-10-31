"""Read-only, stage-gated local inventory for Figure 2.

Prints exactly what exists on Windows E: and what is scientifically missing.
Parquet metadata is read without loading Groundsource millions of rows.
Never equate existence of a GFD/GFID file with verified physical flood truth.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


REQUIRED = {
 "gf10_frozen": ("data/reference/grid10_urban_2020.parquet",
                 ["grid_id","grid_x","grid_y","urban_fraction_2020"]),
 "news_label_primary": ("outputs/labels/groundsource_gf10_primary.parquet",
                        ["grid_id","date","event_id","geocode_quality"]),
 "fig1_city_crosswalk": ("outputs/fig1_v2/fig1_grid_dominant_ucdb.parquet",
                         ["grid_id","city_id"]),
 "fig1_city_v3_audit": ("outputs/fig1_v3_full_r2/ucdb_city_development_holdout.csv",
                       ["city_id","fig1_v3_status","eligible_using_only_development_years"]),
}
DERIVED = {
 "storms_weather_derived": "data/derived/storm_exposure_weather.parquet",
 "static_core_GF10": "data/derived/static_grid_factors.parquet",
 "static_resilience_GF10": "data/derived/fig2_resilience_all_static_GF10.parquet",
 "static_extended_GF10": "data/derived/fig2_extended_grid_factors.parquet",
 "panel_news_proxy": "outputs/panels/storm_exposure_with_news_labels.parquet",
 "weather_contract": "data/derived/fig2_weather_provenance.json",
}
EXPORTS = ("data/gee_exports/fig2_weather",
           "data/gee_exports/fig2_static",
           "data/gee_exports/fig2_exposure")


def check(root,city_audit=None):
    from pyarrow.parquet import ParquetFile
    root=Path(root)
    out={"root":str(root),"status":"INSPECTION_ONLY_NO_VALIDATION",
         "required":{},"derived":{},"gee_downloads":{},
         "physical_verified_pluvial_positives_and_dry_negatives":False}
    for name,(relative,required) in REQUIRED.items():
        path=Path(city_audit) if name=="fig1_city_v3_audit" and city_audit else root/relative
        record={"path":str(path),"exists":path.is_file()}
        if record["exists"]:
            try:
                if path.suffix==".parquet":
                    info=ParquetFile(path)
                    names=set(info.schema_arrow.names)
                    record["metadata_rows"]=int(info.metadata.num_rows)
                else:
                    import pandas as pd
                    hdr=pd.read_csv(path,nrows=0)
                    names=set(hdr.columns)
                record["missing_required_fields"]=sorted(set(required)-names)
                record["schema_pass"]=not record["missing_required_fields"]
            except (OSError,ValueError) as ex:
                record["schema_pass"]=False
                record["error"]=str(ex)[:300]
        out["required"][name]=record
    for name,relative in DERIVED.items():
        p=root/relative
        out["derived"][name]={"path":str(p),"exists":p.is_file()}
    for path in EXPORTS:
        folder=root/path
        files=list(folder.glob("f2_*.csv")) if folder.is_dir() else []
        out["gee_downloads"][path]={"exists":folder.is_dir(),
                                    "matching_csv_file_count":len(files),
                                    "complete_coverage_audited":False}
    out["baseline_ready"]=all(v.get("schema_pass",False) for v in out["required"].values())
    out["model_ready"]=bool(out["baseline_ready"] and all(
       v["exists"] for v in out["derived"].values()))
    out["publication_ready"]=False
    out["next_step"]=("Run Figure2 GF10+city export/sample and one weekly GEE dry-run."
                      if out["baseline_ready"] else
                      "Resolve missing frozen GF10 / Figure1-v3 development audit inputs before GEE.")
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path(r"E:\GEE_flooding"))
    p.add_argument("--city-audit-v3",type=Path,
                   help="Override Figure1-v3 latest versioned development audit")
    a=p.parse_args(argv)
    print(json.dumps(check(a.root,a.city_audit_v3),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
