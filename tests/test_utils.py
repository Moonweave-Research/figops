"""Unit tests for plotting/utils.py — density alpha, label compression, scientific padding."""
# ruff: noqa: I001, E402

import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plotting.utils import (
    apply_density_alpha,
    apply_scientific_padding,
    compress_sample_label,
)


class TestApplyDensityAlpha(unittest.TestCase):
    def test_large_dataset_reduces_alpha(self):
        alpha, size = apply_density_alpha(2000)
        self.assertLess(alpha, 0.6)
        self.assertLess(size, 10)

    def test_medium_dataset(self):
        alpha, size = apply_density_alpha(500)
        self.assertAlmostEqual(alpha, 0.6 * 0.7)
        self.assertAlmostEqual(size, 10 * 0.8)

    def test_small_dataset_uses_base(self):
        alpha, size = apply_density_alpha(50)
        self.assertEqual(alpha, 0.6)
        self.assertEqual(size, 10)

    def test_custom_base_values(self):
        alpha, size = apply_density_alpha(50, base_alpha=1.0, base_size=20)
        self.assertEqual(alpha, 1.0)
        self.assertEqual(size, 20)

    def test_zero_dataset(self):
        alpha, size = apply_density_alpha(0)
        self.assertEqual(alpha, 0.6)
        self.assertEqual(size, 10)


class TestCompressSampleLabel(unittest.TestCase):
    def test_standard_compression(self):
        result = compress_sample_label("Coated Sample_Noa_None_Aligned")
        self.assertEqual(result, "Coated, Noa, None, Aln.")

    def test_non_string_input(self):
        result = compress_sample_label(42)
        self.assertEqual(result, "42")

    def test_empty_string(self):
        result = compress_sample_label("")
        self.assertEqual(result, "")

    def test_no_match_passthrough(self):
        result = compress_sample_label("SimpleLabel")
        self.assertEqual(result, "SimpleLabel")

    def test_unaligned_compression(self):
        result = compress_sample_label("Unaligned")
        self.assertEqual(result, "Unaln.")


class TestApplyScientificPadding(unittest.TestCase):
    def test_positive_data_default(self):
        fig, ax = plt.subplots()
        result = apply_scientific_padding(ax, 100)
        self.assertEqual(result, 160.0)
        y_min, y_max = ax.get_ylim()
        self.assertEqual(y_min, 0)
        self.assertEqual(y_max, 160.0)
        plt.close(fig)

    def test_negative_data_min_expands_bottom(self):
        fig, ax = plt.subplots()
        apply_scientific_padding(ax, 100, data_min=-50)
        y_min, y_max = ax.get_ylim()
        self.assertEqual(y_min, -50 * 1.6)
        self.assertEqual(y_max, 160.0)
        plt.close(fig)

    def test_data_min_zero_stays_zero(self):
        fig, ax = plt.subplots()
        apply_scientific_padding(ax, 100, data_min=0)
        y_min, _ = ax.get_ylim()
        self.assertEqual(y_min, 0)
        plt.close(fig)

    def test_data_min_positive_stays_zero(self):
        fig, ax = plt.subplots()
        apply_scientific_padding(ax, 100, data_min=10)
        y_min, _ = ax.get_ylim()
        self.assertEqual(y_min, 0)
        plt.close(fig)

    def test_custom_padding_ratio(self):
        fig, ax = plt.subplots()
        result = apply_scientific_padding(ax, 100, padding_ratio=2.0)
        self.assertEqual(result, 200.0)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
