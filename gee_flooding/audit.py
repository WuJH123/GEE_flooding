"""Non-download audit of existing local E-drive datasets and completed label products.

All paths from past research are CANDIDATES until checked on the user's computer.
Files under E:\Global_flooding / E:\数据集 are READ-ONLY. Never resample old
20-km positive grid-day labels as the new study's 10-km original events.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from collections import Counter
from .paths import safe_output, atomic_json

KNOWN = [
 ("new_groundsource_original","data/raw/groundsource_2026.parquet","raw WKB","direct_raw"),
 ("new_GF10_frozen","data/reference/grid10_urban_2020.parquet","EPSG6933 10km","direct_gf10"),
 ("new_GF10_qc","data/reference/grid10_qc.json","QC","direct_gf10"),
 ("new_primary_labels","outputs/labels/groundsource_gf10_primary.parquet","10km geocode relations","direct_gf10"),
 ("new_event_audit","outputs/labels/geocode_event_audit.parquet","QC","direct_gf10"),
 ("new_weather_exposure","data/derived/storm_exposure_weather.parquet","10km grid-day","direct_if_schema_valid"),
 ("new_static_grid_factors","data/derived/static_grid_factors.parquet","10km static","direct_if_schema_valid"),
]
HISTORICAL = [
 ("old_groundsource_original",r"E:\数据集\Groundsource_全球城市内涝点位\groundsource_2026.parquet","raw WKB","alternative_source_only"),
 ("old_gridday_20km",r"E:\数据集\Groundsource_全球城市内涝点位\processed\groundsource_gridday_20km.parquet","20km grid-day","NOT_10km_labels"),
 ("old_SMOD_west",r"E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s00.tif","10km raster","reuse_readonly_if_needed"),
 ("old_SMOD_east",r"E:\Global_flooding\grid10\gee_tifs\gf10_smod2020_v1_s01.tif","10km raster","reuse_readonly_if_needed"),
 ("old_M3_urban_catalogue",r"E:\Global_flooding\processed_local\urban_catalogue_m3_pop100_share50.parquet","20km M3","NOT_direct_10km_feature"),
 ("old_GHSL_all_epochs",r"E:\Global_flooding\processed_local\ghsl_all_epochs.parquet","20km x epochs","NOT_direct_10km_feature"),
 ("old_M3_event_controls",r"E:\Global_flooding\episode_control\matched_case_control_m3.parquet","20km M3","NOT_10km_negatives"),
 ("old_M3_event_weather",r"E:\Global_flooding\climate_global\climate_features_primary.parquet","20km event weather","NOT_direct_10km_weather"),
 ("old_M3_complete_climate",r"E:\Global_flooding\climate_local_first\primary_complete_strata.parquet","20km weather strata","NOT_direct_10km_weather"),
 ("old_M3_static_context",r"E:\Global_flooding\mechanism_project\05_static_merged\grid_static_context_m3.parquet","20km M3 static","NOT_direct_10km_feature"),
 ("old_2020_BUILT_M3",r"E:\Global_flooding\mechanism_project\30_urban_context\30c_built_grid_2020.parquet","20km 2020","NOT_direct_10km_feature"),
 ("UCDB_2024",r"E:\数据集\2024城市中心数据库GHS_UCDB_GLOBE_R2024A_V1_1\GHS_UCDB_GLOBE_R2024A.gpkg","city polygons","reuse_readonly"),
 ("SMOD_2025_1km",r"E:\数据集\全球GHS-SMOD定居点模型\GHS_SMOD_E2025_GLOBE_R2023A_54009_1000_V2_0.tif","1km raster EPSG54009","not_gf10_2020"),
]

def known_paths(root):
    root=Path(root)
    return [(name,root/rel,scale,usage) for name,rel,scale,usage in KNOWN]+[
        (name,Path(path),scale,usage) for name,path,scale,usage in HISTORICAL
    ]

def inventory(root):
    entries=[]
    for name,path,scale,usage in known_paths(root):
        d={"name":name,"historical_candidate_path":str(path),
           "exists_on_this_machine":path.is_file(),
           "spatial_unit":scale,"reusability":usage}
        if path.is_file():
            d["size_bytes"]=path.stat().st_size
            if path.suffix.lower()==".parquet":
                import pyarrow.parquet as pq
                meta=pq.read_metadata(path)
                d["parquet_rows"]=meta.num_rows
                d["parquet_columns"]=meta.schema.names
        entries.append(d)
    out=safe_output(root,"reports/qc/local_data_inventory.json")
    atomic_json(out,{"status":"LOCAL_DISCOVERY_ONLY_NO_DOWNLOAD",
                     "source":"known prior dataset locations + fresh file existence checks",
                     "note":"A historical path is not proof of current availability. Reuse is read-only; spatial grids must match.",
                     "files":entries})
    return {"written":str(out),
            "existing":sum(x["exists_on_this_machine"] for x in entries),
            "total_candidates":len(entries)}

def summarize_labels(root,labels=None):
    """SQLite-backed streaming true cardinality audit; no Parquet full-memory load."""
    import pyarrow.parquet as pq
    path=Path(labels) if labels else safe_output(root,"outputs/labels/groundsource_gf10_primary.parquet")
    if not path.is_file():raise FileNotFoundError(path)
    summary=safe_output(root,"reports/qc/label_distribution.json")
    by_year=safe_output(root,"reports/labels_by_year_quality.csv")
    grid_stats=safe_output(root,"reports/top_reported_grids.csv")
    if any(p.exists() for p in (summary,by_year,grid_stats)):
        raise FileExistsError("Distribution outputs already exist; do not overwrite previous audit")
    cache=safe_output(root,"cache/_label_distribution.sqlite")
    cache.parent.mkdir(parents=True,exist_ok=True)
    if cache.exists():raise FileExistsError("Stale SQLite audit cache; inspect before retry: "+str(cache))
    total=0
    db=sqlite3.connect(cache)
    try:
        db.execute("CREATE TABLE obs(event_id TEXT PRIMARY KEY, grid_id TEXT NOT NULL,"
                   " day TEXT NOT NULL, quality TEXT NOT NULL) WITHOUT ROWID")
        pf=pq.ParquetFile(path)
        required={"event_id","grid_id","date","geocode_quality"}
        if not required.issubset(pf.schema_arrow.names):
            raise ValueError("Missing labels fields "+str(required-set(pf.schema_arrow.names)))
        for batch in pf.iter_batches(batch_size=25000,columns=list(required)):
            fields=batch.to_pydict()
            rows=[]
            for id,grid,dt,qual in zip(fields["event_id"],fields["grid_id"],fields["date"],fields["geocode_quality"]):
                if not id or not grid or dt is None or not qual:
                    raise ValueError("Null event/grid/day/quality in primary labels")
                iso=dt.isoformat()[:10]
                if not ("2000-01-01"<=iso<="2025-12-31"):
                    raise ValueError("Unexpected date "+iso)
                rows.append((str(id),str(grid),iso,str(qual)))
            try:db.executemany("INSERT INTO obs VALUES(?,?,?,?)",rows)
            except sqlite3.IntegrityError as e:
                raise ValueError("Duplicate raw event UUID in primary labels") from e
            total+=len(rows)
            if total%250000<25000:print("[READ]",total,flush=True)
        if total!=pf.metadata.num_rows:raise RuntimeError("Incomplete Parquet scan")
        stats=[{"year":int(r[0]),"quality":r[1],"report_rows":r[2],
                "distinct_grids":r[3],"unique_grid_days":r[4]}
               for r in db.execute(
               "SELECT SUBSTR(day,1,4), quality, COUNT(*), COUNT(DISTINCT grid_id),"
               " COUNT(DISTINCT grid_id || ':' || day)"
               " FROM obs GROUP BY SUBSTR(day,1,4), quality ORDER BY 1,2")]
        n_high=db.execute("SELECT COUNT(*) FROM obs WHERE quality='HIGH_GEOCODE_SPECIFICITY'").fetchone()[0]
        high_recent=db.execute("SELECT COUNT(*) FROM obs WHERE quality='HIGH_GEOCODE_SPECIFICITY' AND day>='2021-01-01'").fetchone()[0]
        high_distinct_days=db.execute(
            "SELECT COUNT(*) FROM (SELECT grid_id,day FROM obs"
            " WHERE quality='HIGH_GEOCODE_SPECIFICITY' GROUP BY grid_id,day)").fetchone()[0]
        high_cells=db.execute("SELECT COUNT(DISTINCT grid_id) FROM obs WHERE quality='HIGH_GEOCODE_SPECIFICITY'").fetchone()[0]
        top=db.execute("SELECT grid_id, COUNT(*) AS n FROM obs WHERE quality='HIGH_GEOCODE_SPECIFICITY'"
                       " GROUP BY grid_id ORDER BY n DESC LIMIT 30").fetchall()
        import csv
        by_year.parent.mkdir(parents=True,exist_ok=True)
        with by_year.open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["year","quality","report_rows","distinct_grids","unique_grid_days"])
            writer.writeheader();writer.writerows(stats)
        with grid_stats.open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.writer(f);writer.writerow(["grid_id","high_specificity_news_reports"])
            writer.writerows(top)
        results={"status":"PASS_DISTINCT_EVENT_AND_GRID_DAY_AUDIT",
                 "source_labels":str(path),"primary_rows":total,
                 "high_geocode_records":n_high,
                 "high_geocode_distinct_grid_days":high_distinct_days,
                 "high_geocode_distinct_grid_cells":high_cells,
                 "high_geocode_records_2021_2025":high_recent,
                 "high_geocode_pre2021_records":n_high-high_recent,
                 "spatial_unit":"EPSG:6933 10km broad 2020 urban frame",
                 "caveat":"Raw news UUID not independent meteorological storm, pluvial event or verified inundation."}
        atomic_json(summary,results)
        return results
    finally:
        db.close()
        cache.unlink(missing_ok=True)
