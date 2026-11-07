"""Offline science-gate regressions; no simulated GEE completion claims."""
import sys
import json
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_merit_pilot_audit import SELECTORS, RENAME, check_frame, source_pixel_comparison
from weather_runner import _check_weather_frame
from plan_merit_hybrid_v10 import HERE as V10, MEMBERS as MERIT_MEMBERS, TASKS as MERIT_TASKS, REPORT as MERIT_REPORT, sha
from merit_hybrid_runner import pilot_gate
sys.path.insert(0, r"E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106")
from cee_v8 import core


class ScienceGateTests(unittest.TestCase):
    def merit_frame(self):
        vals = {name: 1.0 for name in SELECTORS[1:]}
        vals.update(merit_permanent_water_fraction=0.2, merit_valid_fraction=1.0,
                    hnd_p10=0.0, hnd_p50=1.0, hnd_p90=2.0,
                    upa_p90=1.0, upa_max=2.0)
        return pd.DataFrame([{"grid_id": "1_2", **vals}])

    def test_merit_member_and_order(self):
        expected = pd.DataFrame({"grid_id": ["1_2"]})
        frame = self.merit_frame()
        self.assertEqual(check_frame(frame, expected)["n_GF10"], 1)
        frame.loc[0, "hnd_p10"] = 3.0
        with self.assertRaisesRegex(ValueError, "quantile ordering"):
            check_frame(frame, expected)

    def test_merit_rejects_duplicate_grid(self):
        frame = pd.concat([self.merit_frame()] * 2, ignore_index=True)
        expected = pd.DataFrame({"grid_id": ["1_2", "2_3"]})
        with self.assertRaisesRegex(ValueError, "member mismatch"):
            check_frame(frame, expected)

    def test_merit_missing_source_is_null_not_false_physical_violation(self):
        valid = self.merit_frame()
        empty = valid.copy()
        empty.loc[0, "grid_id"] = "2_3"
        empty.loc[0, SELECTORS[1:]] = float("nan")
        empty.loc[0, "merit_valid_fraction"] = 0.0
        frame = pd.concat([valid, empty], ignore_index=True)
        expected = pd.DataFrame({"grid_id": ["1_2", "2_3"]})
        quality = check_frame(frame, expected)
        self.assertEqual(quality["source_gap_count"], 1)
        self.assertEqual(quality["missing_per_band"]["hnd_p50"], 1)

    def test_unweighted_native_rejected_against_real_source_pixels(self):
        # Real Greenland source-pixel diagnostic exposed a 1.64% UPA mean bias.
        frame = self.merit_frame()
        frame.loc[0, "grid_id"] = "-500_723"
        frame.loc[0, "merit_upa_mean_km2"] = 14.351716252947107
        outcome = source_pixel_comparison(frame, "-500_723")
        self.assertFalse(outcome["source_pixel_tolerance_pass"])
        self.assertIn("merit_upa_mean_km2", outcome["source_pixel_failures"])

    def test_weighted_native_passes_three_real_source_cells(self):
        source = Path(__file__).resolve().parent / "native_three_source_qc_weighted.json"
        results = json.loads(source.read_text(encoding="utf-8"))["results"]
        reverse = {value: key for key, value in RENAME.items()}
        for item in results:
            row = {reverse.get(name, name): value["GEE_native"]
                   for name, value in item["comparison"].items()}
            row["grid_id"] = item["grid_id"]
            outcome = source_pixel_comparison(pd.DataFrame([row]), item["grid_id"])
            self.assertTrue(outcome["source_pixel_tolerance_pass"], item["grid_id"])

    def test_weather_rejects_incomplete_halfhours(self):
        row = {field: 1.0 for field in core.FIELDS[2:]}
        row.update(grid_id="1_2", date_utc="2021-09-01",
                   imerg_n_obs_day=47, imerg_n_obs_pre7d=336,
                   imerg_n_obs_pre14d=672, imerg_n_obs_pre30d=1440)
        frame = pd.DataFrame([row])
        expected = pd.DataFrame({"grid_id": ["1_2"], "date_utc": ["2021-09-01"]})
        with self.assertRaisesRegex(ValueError, "Incomplete/implausible IMERG"):
            _check_weather_frame(frame, expected)

    def test_weather_rejects_impossible_peak_vs_three_hour(self):
        row = {field: 1.0 for field in core.FIELDS[2:]}
        row.update(grid_id="1_2", date_utc="2021-09-01", imerg_day_mm=2,
                   imerg_peak_30min_mm_h=10, imerg_rolling3h_max_mm=1,
                   imerg_n_obs_day=48, imerg_n_obs_pre7d=336,
                   imerg_n_obs_pre14d=672, imerg_n_obs_pre30d=1440)
        row.update(imerg_pre7d_mm=1, imerg_pre14d_mm=2, imerg_pre30d_mm=3)
        frame = pd.DataFrame([row])
        expected = pd.DataFrame({"grid_id": ["1_2"], "date_utc": ["2021-09-01"]})
        with self.assertRaisesRegex(ValueError, "Incomplete/implausible IMERG"):
            _check_weather_frame(frame, expected)

    def test_real_hybrid_partition_and_failed_westedge_gate(self):
        report = json.loads(MERIT_REPORT.read_text())
        self.assertEqual(report["status"], "FROZEN_GF10_PARTITION_QC_PASS_NO_GLOBAL_SUBMISSION")
        self.assertEqual(report["frozen_GF10"], 1395471)
        self.assertEqual(report["seam_quarantine_GF10"], 450)
        self.assertEqual(report["direct_GF10"] + report["native_GF10"] +
                         report["pilot_submitted_GF10"] + 450, 1395471)
        self.assertEqual(sha(MERIT_MEMBERS), report["members_sha256"])
        self.assertEqual(sha(MERIT_TASKS), report["tasks_sha256"])
        self.assertEqual(report["pilot_states"]["westedge"], "GEE_FAILED")
        self.assertTrue(pilot_gate()["westedge_direct_failure_quarantined"])


if __name__ == "__main__":
    unittest.main()
