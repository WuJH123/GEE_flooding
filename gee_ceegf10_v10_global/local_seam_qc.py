"""Offline regressions against the real 450-GF10 seam source-pixel products."""
import json
import unittest
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


class SeamRecoveryTests(unittest.TestCase):
    def test_all_16_source_metrics_match_three_accepted_nonseam_cells(self):
        report = json.loads((HERE / "seam_source_16_validation.json").read_text())
        self.assertEqual(report["status"], "RAW_SOURCE_ALL_16_NON_SEAM_VALIDATION_PASS")
        self.assertEqual(len(report["references"]), 3)
        for item in report["references"]:
            self.assertEqual(item["n_metrics"], 16)
            self.assertEqual(item["failures"], [])

    def test_450_frozen_seam_ids_and_source_gaps(self):
        report = json.loads((HERE / "merit_seam450_audit.json").read_text())
        self.assertEqual(report["status"], "SEAM450_SOURCE_PIXEL_QC_PASS_FOR_GLOBAL_ASSEMBLY")
        self.assertEqual(report["n_parents"], 14)
        self.assertEqual(report["n_GF10"], 450)
        self.assertEqual(report["source_gap_rows"], 3)
        frame = pd.read_parquet(HERE / "merit_seam450_SOURCE_QC_PASS.parquet")
        self.assertEqual(len(frame), 450)
        self.assertFalse(frame.grid_id.duplicated().any())
        self.assertEqual(int(frame.merit_valid_fraction.eq(0).sum()), 3)
        self.assertTrue(frame.loc[frame.merit_valid_fraction.eq(0),
                                  "merit_hand_mean_m"].isna().all())

    def test_grouped_seam_source_matches_independent_one_cell(self):
        reference = json.loads((HERE / "seam_exact_source_-1737_-214.json").read_text())
        product = pd.read_parquet(HERE / "merit_seam450_SOURCE_QC_PASS.parquet")
        actual = product.set_index("grid_id").loc["-1737_-214"]
        for band, value in reference["metrics"].items():
            self.assertAlmostEqual(float(actual[band]), float(value), places=7, msg=band)


if __name__ == "__main__":
    unittest.main()
