"""Unit tests for plotting/utils.py — density alpha, label compression, scientific padding."""
# ruff: noqa: I001, E402

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from hub_core.geometry_diagnostics import diagnose_figure_geometry

from plotting.utils import (
    apply_density_alpha,
    apply_scientific_padding,
    compress_sample_label,
    place_point_labels,
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


class TestPlacePointLabels(unittest.TestCase):
    def test_helper_is_exported_from_plotting_package(self):
        from plotting import place_point_labels as exported

        self.assertIs(exported, place_point_labels)

    def test_places_crowded_point_labels_with_leader_metadata(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        xs = [0.50, 0.505, 0.51]
        ys = [0.50, 0.50, 0.50]
        ax.set_xlim(0.45, 0.56)
        ax.set_ylim(0.46, 0.56)
        ax.scatter(xs, ys, s=220)

        result = place_point_labels(ax, xs, ys, ["S70", "S75", "S80"], leader=True, min_leader_distance_px=1)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()

        self.assertEqual(len(result["texts"]), 3)
        self.assertGreaterEqual(len(result["leaders"]), 1)
        for text, x, y in zip(result["texts"], xs, ys):
            self.assertEqual(text._graph_hub_leader_target_data, (x, y))
            self.assertTrue(text._graph_hub_leader_connected)
            text_center = text.get_window_extent(renderer).get_points().mean(axis=0)
            target_px = ax.transData.transform((x, y))
            self.assertGreater(float(((text_center - target_px) ** 2).sum() ** 0.5), 4.0)
        plt.close(fig)

    def test_leader_false_labels_do_not_get_overlap_suppression(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0.45, 0.60)
        ax.set_ylim(0.45, 0.55)
        ax.scatter([0.5], [0.5], s=5000)

        result = place_point_labels(ax, [0.5], [0.5], ["S70"], leader=False, initial_offset_px=1)
        fig.canvas.draw()
        checks = diagnose_figure_geometry(fig, [ax], layout_locked=False)["checks"]
        check = next(c for c in checks if c["name"] == "artist_overlaps")

        self.assertFalse(result["texts"][0]._graph_hub_leader_connected)
        self.assertFalse(check["passed"])
        plt.close(fig)

    def test_leader_connected_is_tracked_per_text(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.scatter([0.5, 0.6], [0.5, 0.5], s=300)

        def fake_adjust_text(texts, **_kwargs):
            return texts, [SimpleNamespace(patchA=texts[0])]

        with patch("adjustText.adjust_text", side_effect=fake_adjust_text):
            result = place_point_labels(ax, [0.5, 0.6], [0.5, 0.5], ["S70", "S75"], leader=True)

        self.assertTrue(result["texts"][0]._graph_hub_leader_connected)
        self.assertFalse(result["texts"][1]._graph_hub_leader_connected)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
