"""Fast, fail-closed Figure 1 preflight using existing E-drive data only.

No full polygon remapping, no downloading, no GEE submission. Metadata row
counts are checked BEFORE expensive processing. Nothing written outside ROOT.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import pandas as pd
import pyarrow.parquet as pq
from .paths import safe_output,atomic_json

EXPECTED={"raw_news":2646302,"mapped_news":2202651,"urban_cells":166414}
REQUIRED={
 "raw":{"uuid","geometry","area_km2","start_date","end_date"},
 "mapped":{"event_id","grid_id","date","primary_overlap","n_candidate_cells","geocode_quality"},
 "grid":{"grid_id","grid_x","grid_y","longitude","latitude"},
 "city":{"city_id","continent","koppen_broad","fig1_v3_status"},
}
def _meta(path,need):
    p=Path(path)
    if not p.is_file():raise FileNotFoundError(str(p))
    f=pq.ParquetFile(str(p))
    names=set(f.schema_arrow.names)
    if need-names:raise ValueError(f"Missing parquet fields in {p}: {sorted(need-names)}")
    return {"path":str(p),"rows":f.metadata.num_rows,"columns":sorted(names),
            "bytes":p.stat().st_size}

def _hash_small(path):
    """SHA256 small metadata file; large Parquets are not read just for hashing."""
    p=Path(path)
    if p.stat().st_size>100*1024*1024:return "NOT_HASHED_LARGE_INPUT"
    sha=hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda:fh.read(4*1024*1024),b""):sha.update(block)
    return sha.hexdigest()

def inspect(root,raw,mapped,grid,city,v3qc,v2cross,tag="fig1_preflight_r1"):
    """Audit exact input paths, schemas, conservation, external-dependence flags."""
    dest=safe_output(root,f"outputs/{tag}/preflight")
    if dest.exists():raise FileExistsError(dest)
    meta={
       "raw":_meta(raw,REQUIRED["raw"]),
       "mapped":_meta(mapped,REQUIRED["mapped"]),
       "grid":_meta(grid,REQUIRED["grid"]),
    }
    city=Path(city)
    if not city.exists():raise FileNotFoundError(str(city))
    c=pd.read_csv(city,nrows=5)
    if REQUIRED["city"]-set(c):raise ValueError("v3 city audit missing fields "+
                                             str(sorted(REQUIRED["city"]-set(c))))
    external=json.loads(Path(v3qc).read_text(encoding="utf-8"))
    if not Path(v2cross).is_file():raise FileNotFoundError(v2cross)
    if external.get("sensitivity_is_full_data") is not True:
        raise ValueError("v3 GFID QC is not full-data")
    if external.get("gfid_audit",{}).get("raw_rows")!=136642:
        raise ValueError("v3 GFID source ledger does not contain all 136642 rows")
    for key,actual in [("raw_news",meta["raw"]["rows"]),
                       ("mapped_news",meta["mapped"]["rows"]),
                       ("urban_cells",meta["grid"]["rows"])]:
        if actual!=EXPECTED[key]:
            raise ValueError(f"{key} changed from frozen audited inputs: "
                             f"{actual} != {EXPECTED[key]}")
    origin_counts=external.get("city_audit",{})
    if int(origin_counts.get("all_high_reports",0)) !=1788759:
        raise ValueError("Unexpected HIGH label count in v3 QC")
    if int(origin_counts.get("assigned_high_reports",0)) + int(
       origin_counts.get("unassigned_high_reports",0)) !=1788759:
        raise ValueError("UCDB-high record accounting fails")
    report={"status":"PASS_INPUT_METADATA_AND_SOURCE_LEDGER",
      "checks":meta,
      "v3_qc_sha256":_hash_small(v3qc),
      "v3_city_source":str(city),"v2_crosswalk":str(v2cross),
      "high_uuids":1788759,
      "ucdb_unassigned_high":int(origin_counts["unassigned_high_reports"]),
      "raw_expected":EXPECTED,
      "critical_caveats":[
        "This checks file metadata, NOT per-row raw geometry correctness",
        "Existing 10km grid/domain was frozen from 2020 SMOD only",
        "GFID is external catalogue concordance, NOT independent inundation truth",
        "Source news records are NOT distinct meteorological storms"],
      "next":"Run fig1 publication pipeline; then label review and verified physical cases"
    }
    dest.mkdir(parents=True,exist_ok=False)
    atomic_json(dest/"fig1_input_preflight.json",report)
    return report
