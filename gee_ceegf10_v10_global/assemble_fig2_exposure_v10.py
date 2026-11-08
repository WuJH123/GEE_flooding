"""Join only independently accepted static and event-date exposure products."""
from __future__ import annotations

import json

import pandas as pd

from merit_direct_raster_pilot import HERE
from plan_merit_hybrid_v10 import sha


def main():
    merit_qc = json.loads((HERE / "merit_independent_post_assembly_qc.json").read_text())
    weather_qc = json.loads((HERE / "weather_independent_post_assembly_qc.json").read_text())
    if merit_qc["status"] != "INDEPENDENT_GLOBAL_MERIT_QC_PASS" or \
       weather_qc["status"] != "INDEPENDENT_POST_ASSEMBLY_QC_PASS":
        raise ValueError("Source science QC gate not passed")
    merit_path = HERE / "merit_hydro_GLOBAL_QC_PASS.parquet"
    weather_path = HERE / "weather_exposure_GLOBAL_QC_PASS.parquet"
    if sha(merit_path) != merit_qc["output_sha256"] or \
       sha(weather_path) != weather_qc["product_sha256"]:
        raise ValueError("Source Parquet fingerprint changed")
    static = pd.read_parquet(merit_path)
    events = pd.read_parquet(weather_path)
    if static.grid_id.duplicated().any() or events[["grid_id", "date_utc"]].duplicated().any():
        raise ValueError("Source key uniqueness changed")
    joined = events.merge(static, on="grid_id", how="left", validate="many_to_one", indicator=True)
    if len(joined) != len(events) or not joined._merge.eq("both").all():
        raise ValueError("Weather row has no frozen global MERIT GF10")
    joined = joined.drop(columns="_merge")
    if joined[["grid_id", "date_utc"]].duplicated().any():
        raise ValueError("Joined exposure has duplicate GF10 UTC date")
    output = HERE / "fig2_GF10_event_exposure_MERIT_IMERG_ERA5_QC_PASS.parquet"
    joined.to_parquet(output, index=False)
    report = {"status": "FIG2_GF10_EVENT_EXPOSURE_JOIN_QC_PASS",
              "rows": len(joined), "unique_GF10": joined.grid_id.nunique(),
              "columns": joined.columns.tolist(),
              "merit_source_gap_event_rows": int(joined.merit_valid_fraction.fillna(0).eq(0).sum()),
              "ERA5_soil_l1_missing_rows": int(joined.era5_soil_l1_prevday_m3m3.isna().sum()),
              "reported_or_unlabeled_exposure_not_true_flood_negative": True,
              "source_merit_sha256": merit_qc["output_sha256"],
              "source_weather_sha256": weather_qc["product_sha256"],
              "output": str(output), "output_sha256": sha(output)}
    (HERE / "fig2_event_exposure_join_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
