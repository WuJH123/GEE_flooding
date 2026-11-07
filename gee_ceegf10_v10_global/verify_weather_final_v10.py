"""Independent post-assembly invariants for the accepted event exposure table."""
import json

import pandas as pd

from merit_direct_raster_pilot import HERE, ROOT
from plan_merit_hybrid_v10 import sha


def main():
    product = HERE / "weather_exposure_GLOBAL_QC_PASS.parquet"
    prior = json.loads((HERE / "weather_assembly_report.json").read_text())
    if prior["status"] != "GLOBAL_SCIENTIFIC_QC_PASS" or sha(product) != prior["output_sha256"]:
        raise ValueError("Accepted weather source fingerprint changed")
    frame = pd.read_parquet(product)
    grid = pd.read_parquet(ROOT / "gee_ceegf10_v1/gf10_global_nonantarctic_land.parquet",
                           columns=["grid_id"])
    if len(frame) != prior["accepted_rows"] or frame[["grid_id", "date_utc"]].duplicated().any():
        raise ValueError("Weather grid/date count or uniqueness changed")
    if not frame.grid_id.isin(grid.grid_id).all():
        raise ValueError("Weather output references absent frozen GF10 IDs")
    counts = {"imerg_n_obs_day": 48, "imerg_n_obs_pre7d": 336,
              "imerg_n_obs_pre14d": 672, "imerg_n_obs_pre30d": 1440}
    for name, expected in counts.items():
        if frame[name].isna().any() or not frame[name].eq(expected).all():
            raise ValueError("IMERG window count failed: " + name)
    nonnegative = ["imerg_day_mm", "imerg_peak_30min_mm_h", "imerg_rolling3h_max_mm",
                   "imerg_pre7d_mm", "imerg_pre14d_mm", "imerg_pre30d_mm",
                   "era5_rain_prevday_mm", "era5_runoff_prevday_mm"]
    for name in nonnegative:
        if frame[name].dropna().lt(0).any():
            raise ValueError("Negative physical accumulation: " + name)
    if frame.imerg_rolling3h_max_mm.gt(frame.imerg_day_mm + 1e-4).any():
        raise ValueError("Same-day 3h rainfall exceeds daily rainfall")
    report = {"status": "INDEPENDENT_POST_ASSEMBLY_QC_PASS",
              "rows": len(frame), "unique_GF10": frame.grid_id.nunique(),
              "frozen_GF10_rows": len(grid), "outside_frozen_GF10": 0,
              "complete_IMERG_window_counts": counts,
              "ERA5_soil_l1_missing_rows": int(frame.era5_soil_l1_prevday_m3m3.isna().sum()),
              "negative_accumulation_rows": 0, "three_hour_greater_than_day_rows": 0,
              "product_sha256": sha(product),
              "event_dates_are_reported_or_unlabeled_candidates_not_true_negatives": True}
    (HERE / "weather_independent_post_assembly_qc.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
