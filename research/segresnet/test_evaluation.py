"""Tiny in-memory native-grid tests; no data, GPU, application DB or model."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from evaluation import aggregate, metrics, native_prediction


class NativeEvaluationTests(unittest.TestCase):
    def test_undefined_is_null_and_legitimate_zero_remains_zero(self):
        self.assertEqual(metrics(dict(tp=0, fp=0, fn=0)), dict.fromkeys(("dice", "iou", "precision", "recall")))
        self.assertEqual(metrics(dict(tp=0, fp=1, fn=1)), dict.fromkeys(("dice", "iou", "precision", "recall"), 0))

    def test_macro_does_not_become_pooled_and_exclusions_remain_visible(self):
        rows = []
        for case, counts in [("a", dict(tp=1, fp=1, fn=0, tn=5)), ("b", dict(tp=9, fp=0, fn=0, tn=5))]:
            rows.append(dict(dataset_case_id=case, metrics=metrics(counts), confusion_counts=counts))
        rows.append(dict(dataset_case_id="c", metrics=dict.fromkeys(("dice", "iou", "precision", "recall")), exclusion_reason="synthetic failure"))
        result = aggregate(rows)
        self.assertAlmostEqual(result["macro_metrics"]["dice"], (2/3 + 1)/2)
        self.assertAlmostEqual(result["pooled_micro_metrics"]["dice"], 20/21)
        self.assertEqual(result["case_count"], 3)
        self.assertEqual(result["included_case_count"], 2)
        self.assertEqual(result["exclusions"][0]["dataset_case_id"], "c")

    def test_macro_has_per_metric_denominator(self):
        counts = dict(tp=0, fp=0, fn=1, tn=5)
        result = aggregate([dict(dataset_case_id="a", metrics=metrics(counts), confusion_counts=counts)])
        self.assertIsNone(result["macro_metrics"]["precision"])
        self.assertEqual(result["macro_metrics"]["recall"], 0)
        self.assertEqual(result["macro_denominators"]["precision"]["undefined_cases"], 1)

    def test_identity_native_slabs_match_independent_boolean_grid(self):
        probability = np.zeros((5, 6, 7), dtype=np.float32)
        probability[1:4, 2:5, 2:6] = .75
        expected = probability >= .5
        for start, stop in [(0, 2), (2, 5), (5, 7)]:
            actual = native_prediction(probability, np.eye(4), np.eye(4), expected.shape, start, stop)
            np.testing.assert_array_equal(actual, expected[:, :, start:stop])

    def test_anisotropic_flipped_oblique_affine_uses_native_coordinates(self):
        # Both grids use the same rotated/flipped physical axes, but native
        # increments are half cached increments. Expected foreground is defined
        # independently by native index i>=4, not by inverse-affine round-trip.
        angle = .43
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        cache = np.eye(4)
        cache[:3, :3] = rotation @ np.diag([-1., 1., 1.])
        cache[:3, 3] = [20, -15, 5]
        native = cache.copy()
        native[:3, :3] = cache[:3, :3] @ np.diag([.5, 1, .5])
        probability = np.zeros((5, 5, 5), dtype=np.float32)
        probability[2:] = 1
        result = native_prediction(probability, cache, native, (9, 5, 9), 0, 9)
        # Exact half-probability i=3 belongs to >=0.5; use interior nodes to
        # avoid floating-point boundary and source-extent comparisons.
        self.assertTrue(result[4:8, 1:4, 1:8].all())
        self.assertFalse(result[:2, 1:4, 1:8].any())

    def test_probability_validation_and_background_outside_source(self):
        probability = np.ones((3, 3, 3), dtype=np.float32)
        native = np.eye(4)
        native[0, 3] = 10
        self.assertFalse(native_prediction(probability, np.eye(4), native, (3, 3, 3), 0, 3).any())
        for value in [np.nan, np.inf, -1., 2.]:
            probability[1, 1, 1] = value
            with self.assertRaises(ValueError):
                native_prediction(probability, np.eye(4), native, (3, 3, 3), 0, 3)


if __name__ == "__main__":
    unittest.main()
