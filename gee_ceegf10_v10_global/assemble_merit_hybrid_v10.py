"""Assemble only real MERIT GeoTIFF/CSV results that passed frozen science QC."""
import json
import sqlite3

import numpy as np
import pandas as pd
import rasterio

from merit_direct_raster_pilot import HERE, ROOT, SITES
from merit_hybrid_runner import DB, OUT
from plan_merit_hybrid_v10 import GRID, MEMBERS, REPORT, sha
from merit_highlat_split_v10 import OUT as SPLIT_OUT, OLD_PILOT

import sys
sys.path.insert(0, str(ROOT / "CEE_GF10_GLOBAL_EE_V8_20261106"))
from cee_v8 import core  # noqa: E402


def pilot_frame(site: str) -> tuple[pd.DataFrame, dict]:
    directory = HERE / "merit_direct_pilots" / site
    audit = json.loads((directory / "audit.json").read_text())
    if audit["status"] != "SCIENTIFIC_QC_PASS_DIRECT_RASTER_PILOT":
        raise ValueError("Pilot not scientifically accepted: " + site)
    intent = json.loads((directory / "intent.json").read_text())
    source = directory / (intent["name"] + ".tif")
    if not source.is_file():
        raise FileNotFoundError(source)
    cells = pd.read_parquet(directory / "input_GF10.parquet")
    x, y = SITES[site]
    with rasterio.open(source) as raster:
        if raster.count != 16 or raster.width != 60 or raster.height != 60 or raster.crs.to_epsg() != 6933:
            raise ValueError("Accepted pilot raster metadata drift")
        pixels = raster.read(masked=True)
    values = []
    for cell in cells.itertuples(index=False):
        xi = int(cell.grid_x) - x
        yi = y + 60 - int(cell.grid_y) - 1
        if not (0 <= xi < 60 and 0 <= yi < 60):
            raise ValueError("Pilot GF10 raster index mismatch")
        values.append([str(cell.grid_id)] +
                      [np.nan if pixels.mask[i, yi, xi] else float(pixels[i, yi, xi])
                       for i in range(16)])
    return pd.DataFrame(values, columns=["grid_id"] + core.BANDS), {
        "source": site, "source_sha256": sha(source), "n_GF10": len(values)}


def highlat_probe_frame() -> tuple[pd.DataFrame, dict]:
    audit = json.loads((OLD_PILOT / "audit.json").read_text())
    intent = json.loads((OLD_PILOT / "intent.json").read_text())
    path = OLD_PILOT / (intent["name"] + ".tif")
    cells = pd.read_parquet(OLD_PILOT / "input_GF10.parquet")
    if (audit["status"] != "SCIENTIFIC_QC_PASS_30X30_HIGH_LAT" or
        audit["task_id"] != intent["task_id"] or
        sha(path) != audit["source_SHA256"] or
        sha(OLD_PILOT / "input_GF10.parquet") != intent["input_sha256"] or
        len(cells) != 386):
        raise ValueError("Accepted high-lat pilot source drift")
    with rasterio.open(path) as ds:
        if ds.count != 16 or ds.width != 30 or ds.height != 30 or ds.crs.to_epsg() != 6933:
            raise ValueError("High-lat pilot raster geometry drift")
        pixels = ds.read(masked=True)
    values = []
    for cell in cells.itertuples(index=False):
        xi = int(cell.grid_x) + 660
        yi = 660 - int(cell.grid_y) - 1
        values.append([str(cell.grid_id)] +
                      [np.nan if pixels.mask[i, yi, xi] else float(pixels[i, yi, xi])
                       for i in range(16)])
    return pd.DataFrame(values, columns=["grid_id"] + core.BANDS), {
        "source": "HIGH_LAT_PROBE_REUSED", "source_sha256": sha(path), "n_GF10": len(values)}


def main():
    partition = json.loads(REPORT.read_text())
    if sha(MEMBERS) != partition["members_sha256"] or sha(GRID) != partition["GF10_sha256"]:
        raise ValueError("Frozen source or plan fingerprint changed")
    ownership = pd.read_parquet(MEMBERS)
    pieces, manifests = [], []
    for site in ("wuhan", "coast"):
        frame, item = pilot_frame(site)
        frame["source_task_key"] = "PILOT_" + site.upper()
        pieces.append(frame)
        manifests.append(item)
    conn = sqlite3.connect(DB)
    accepted = conn.execute("SELECT task_key,local_sha FROM jobs WHERE state='QC_PASS' ORDER BY task_key").fetchall()
    for key, fingerprint in accepted:
        path = OUT / key / "merit_QC_PASS.parquet"
        audit = json.loads((OUT / key / "audit.json").read_text())
        if audit["status"] != "QC_PASS" or sha(path) != fingerprint or audit["parquet_sha256"] != fingerprint:
            raise ValueError("Accepted global task file/audit fingerprint drift: " + key)
        frame = pd.read_parquet(path)
        frame["source_task_key"] = key
        pieces.append(frame)
        manifests.append({"source": key, "source_sha256": fingerprint, "n_GF10": len(frame)})
    highlat, highlat_manifest = highlat_probe_frame()
    highlat["source_task_key"] = "MD10_-11_10"
    pieces.append(highlat)
    manifests.append(highlat_manifest)
    split_accepted = 0
    if SPLIT_OUT.exists():
        for directory in sorted(SPLIT_OUT.iterdir()):
            if not directory.is_dir() or not (directory / "audit.json").is_file():
                continue
            audit = json.loads((directory / "audit.json").read_text())
            if audit.get("status") != "QC_PASS":
                continue
            intent = json.loads((directory / "intent.json").read_text())
            path = directory / "merit_QC_PASS.parquet"
            if (audit["task_id"] != intent["task_id"] or
                sha(path) != audit["parquet_sha256"] or
                sha(directory / "input_GF10.parquet") != intent["input_sha256"]):
                raise ValueError("Accepted high-lat split fingerprint drift: " + directory.name)
            frame = pd.read_parquet(path)
            expected_ids = set(pd.read_parquet(directory / "input_GF10.parquet").grid_id.astype(str))
            if len(frame) != audit["n_GF10"] or set(frame.grid_id.astype(str)) != expected_ids:
                raise ValueError("High-lat split GF10 member mismatch: " + directory.name)
            frame["source_task_key"] = intent["parent"]
            pieces.append(frame)
            manifests.append({"source": directory.name,
                              "source_sha256": audit["parquet_sha256"], "n_GF10": len(frame)})
            split_accepted += 1
    result = pd.concat(pieces, ignore_index=True)
    if result.grid_id.duplicated().any() or len(result) != sum(x["n_GF10"] for x in manifests):
        raise ValueError("Duplicate or lost MERIT GF10 rows")
    expected = ownership.loc[ownership.task_key.isin(result.source_task_key.unique()),
                             ["grid_id", "task_key"]]
    check = result[["grid_id", "source_task_key"]].merge(
        expected, on="grid_id", how="left", validate="one_to_one")
    if check.task_key.isna().any() or not (check.source_task_key == check.task_key).all():
        raise ValueError("Accepted MERIT GF10 not assigned to its frozen task")
    if not set(core.BANDS) <= set(result):
        raise ValueError("Incomplete 16 frozen MERIT indicators")
    grid = pd.read_parquet(GRID, columns=["grid_id", "grid_x", "grid_y",
                                          "land_area_km2", "land_fraction"])
    result = result.merge(grid, on="grid_id", how="left", validate="one_to_one")
    if result.land_area_km2.isna().any():
        raise ValueError("MERIT output references absent frozen GF10")
    result = result[["grid_id", "grid_x", "grid_y", "land_area_km2", "land_fraction",
                     "source_task_key"] + core.BANDS]
    completed_safe = len(result) == partition["safe_GF10"]
    status = "ALL_SAFE_QC_PASS_SEAM_450_QUARANTINED" if completed_safe else "PARTIAL_SAFE_QC_PASS"
    output = HERE / ("merit_hydro_SAFE_QC_PASS.parquet" if completed_safe else
                     "merit_hydro_SAFE_PARTIAL_QC_PASS.parquet")
    result.to_parquet(output, index=False)
    report = {"status": status, "frozen_GF10": partition["frozen_GF10"],
              "safe_GF10": partition["safe_GF10"], "accepted_GF10": len(result),
              "safe_coverage_fraction": len(result) / partition["safe_GF10"],
              "all_land_coverage_fraction": len(result) / partition["frozen_GF10"],
              "seam_quarantine_GF10": 450, "new_task_QC_PASS": len(accepted),
              "highlat_split_QC_PASS": split_accepted,
              "highlat_pilot_reused_GF10": 386,
              "source_gap_rows": int(result.merit_valid_fraction.fillna(0).eq(0).sum()),
              "missing_per_band": {name: int(result[name].isna().sum()) for name in core.BANDS},
              "output": str(output), "output_sha256": sha(output),
              "sources": manifests, "only_QC_PASS_results_included": True}
    (HERE / "merit_hydro_assembly_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))


if __name__ == "__main__":
    main()
