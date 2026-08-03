import json
import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from hub_core.geometry_artist_overlaps import (  # noqa: E402
    _line_overlap_boxes,
    _line_overlap_segments,
    _line_segment_resolver,
    _pair_centerline_intersection_px,
)
from hub_core.geometry_diagnostics import diagnose_figure_geometry  # noqa: E402


def _diagonal_figure(legend_loc: str):
    """Build a diagonal whose padded AABB contains the legend."""

    fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
    ax.plot([0, 3], [2, 0], "b-.", label="contact resistance")
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 2)
    ax.legend(loc=legend_loc)
    fig.canvas.draw()
    return fig, ax


class Issue234GeometryTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_diagonal_bbox_iou_is_corrected_by_centerline_fact(self):
        fig, ax = _diagonal_figure("lower left")
        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        pairs = [
            pair
            for pair in measurement["value"]["pairs"]
            if "legend" in (pair["a"], pair["b"])
            and (pair["a"].startswith("line:") or pair["b"].startswith("line:"))
        ]
        self.assertTrue(pairs, "expected a legend/line pair from the diagonal's AABB")
        for pair in pairs:
            # Keep the legacy bbox candidate ratio for compatibility.
            self.assertGreater(pair["iou"], 0.0)
            # Exact centerline evidence distinguishes the bbox artifact.
            self.assertEqual(pair["centerline_intersection_px"], 0.0)
            self.assertFalse(pair["centerline_intersects"])
        self.assertNotIn("threshold", json.dumps(measurement))
        self.assertNotIn("passed", json.dumps(measurement))

    def test_real_line_legend_collision_still_reports_positive_centerline(self):
        fig, ax = _diagonal_figure("center")
        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        pairs = [
            pair
            for pair in measurement["value"]["pairs"]
            if "legend" in (pair["a"], pair["b"])
            and (pair["a"].startswith("line:") or pair["b"].startswith("line:"))
        ]
        self.assertTrue(pairs)
        self.assertTrue(any(pair["centerline_intersects"] for pair in pairs))

    def test_legacy_artist_overlap_keeps_bbox_projection(self):
        fig, ax = _diagonal_figure("lower left")
        legacy = diagnose_figure_geometry(fig, [ax], layout_locked=False)
        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")

        legacy_check = next(item for item in legacy["checks"] if item["name"] == "artist_overlaps")
        legacy_pair = next(
            pair
            for pair in legacy_check["data"]["overlaps"]
            if "legend" in (pair["a"], pair["b"])
            and (pair["a"].startswith("line:") or pair["b"].startswith("line:"))
        )
        raw_measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        raw_pair = next(
            pair
            for pair in raw_measurement["value"]["pairs"]
            if {pair["a"], pair["b"]} == {legacy_pair["a"], legacy_pair["b"]}
        )

        # The legacy projection intentionally keeps its AABB verdict and IoU;
        # exact centerline facts are additive on the raw evidence surface.
        self.assertFalse(legacy_check["passed"])
        self.assertEqual(legacy_pair["iou"], raw_pair["iou"])
        self.assertNotIn("centerline_intersects", legacy_pair)
        self.assertFalse(raw_pair["centerline_intersects"])

    def test_non_line_pairs_carry_no_centerline_field(self):
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
        ax.text(0.5, 0.5, "alpha", ha="center", va="center")
        ax.text(0.52, 0.5, "beta", ha="center", va="center")
        fig.canvas.draw()

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        for pair in measurement["value"]["pairs"]:
            if pair["a"].startswith("line:") or pair["b"].startswith("line:"):
                continue
            self.assertNotIn("centerline_intersection_px", pair)
            self.assertNotIn("centerline_intersects", pair)

    def test_segment_boxes_and_endpoints_share_one_index(self):
        fig, ax = _diagonal_figure("lower left")
        line = ax.get_lines()[0]
        segments = _line_overlap_segments(ax, line)
        boxes = _line_overlap_boxes(ax, line)
        self.assertEqual(len(segments), len(boxes))
        for (box, start, end), legacy_box in zip(segments, boxes):
            self.assertEqual(list(box.extents), list(legacy_box.extents))
            for point in (start, end):
                self.assertGreaterEqual(float(point[0]), box.x0)
                self.assertLessEqual(float(point[0]), box.x1)
                self.assertGreaterEqual(float(point[1]), box.y0)
                self.assertLessEqual(float(point[1]), box.y1)

    def test_resolver_rejects_unknown_and_out_of_range_labels(self):
        fig, ax = _diagonal_figure("lower left")
        resolve = _line_segment_resolver(ax)
        self.assertIsNotNone(resolve("line:0[0]"))
        self.assertIsNone(resolve("legend"))
        self.assertIsNone(resolve("text:'x'"))
        self.assertIsNone(resolve("line:9[0]"))
        self.assertIsNone(resolve("line:0[999]"))

    def test_nan_gap_keeps_legacy_box_but_withholds_centerline_fact(self):
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
        ax.plot([0.0, 1.0, np.nan, 2.0, 3.0], [0.0, 1.0, np.nan, 2.0, 3.0])
        ax.text(1.5, 1.5, "gap", ha="center", va="center")
        fig.canvas.draw()

        # The historical finite-point filter still emits the synthetic
        # cross-gap AABB (so candidate discovery remains compatible), but the
        # exact resolver refuses to turn that gap into a real line segment.
        segments = _line_overlap_segments(ax, ax.get_lines()[0])
        self.assertEqual(len(segments), 3)
        self.assertIsNone(segments[1][1])
        self.assertIsNone(segments[1][2])
        resolve = _line_segment_resolver(ax)
        self.assertIsNone(resolve("line:0[1]"))
        gap_box = segments[1][0]
        target_box = Bbox.from_extents(gap_box.x0, gap_box.y0, gap_box.x1, gap_box.y1)
        self.assertIsNone(
            _pair_centerline_intersection_px(resolve, "line:0[1]", gap_box, "text:'gap'", target_box)
        )
        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        gap_pairs = [
            pair
            for pair in measurement["value"]["pairs"]
            if {pair["a"], pair["b"]} == {"text:'gap'", "line:0[1]"}
        ]
        self.assertEqual(len(gap_pairs), 1)
        self.assertNotIn("centerline_intersection_px", gap_pairs[0])
        self.assertNotIn("centerline_intersects", gap_pairs[0])

    def test_reference_line_centerline_uses_artist_transform(self):
        for reference_kind in ("h", "v"):
            with self.subTest(reference_kind=reference_kind):
                fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
                ax.set_xlim(10, 20)
                ax.set_ylim(100, 200)
                if reference_kind == "h":
                    ax.axhline(150, linewidth=0.5)
                else:
                    ax.axvline(15, linewidth=0.5)
                text = ax.text(15, 150, "reference", ha="center", va="center")
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                line = ax.get_lines()[0]
                segments = _line_overlap_segments(ax, line)
                target_box = text.get_window_extent(renderer)
                resolve = _line_segment_resolver(ax)
                measured = _pair_centerline_intersection_px(
                    resolve, "line:0[0]", segments[0][0], "text:'reference'", target_box
                )
                self.assertIsNotNone(measured)
                self.assertGreater(measured, 0.0)

    def test_pair_with_two_line_segments_is_not_measured(self):
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
        ax.plot([0, 1], [0, 1])
        ax.plot([0, 1], [1, 0])
        fig.canvas.draw()
        resolve = _line_segment_resolver(ax)
        box = Bbox.from_extents(0.0, 0.0, 1.0, 1.0)
        self.assertIsNone(
            _pair_centerline_intersection_px(resolve, "line:0[0]", box, "line:1[0]", box)
        )

    def test_centerline_length_matches_direct_geometry(self):
        fig, ax = _diagonal_figure("center")
        resolve = _line_segment_resolver(ax)
        legend_box = ax.get_legend().get_window_extent(fig.canvas.get_renderer())
        segments = _line_overlap_segments(ax, ax.get_lines()[0])
        box, start, end = segments[0]
        measured = _pair_centerline_intersection_px(
            resolve, "legend", legend_box, "line:0[0]", box
        )
        self.assertIsNotNone(measured)
        mirrored = _pair_centerline_intersection_px(
            resolve, "line:0[0]", box, "legend", legend_box
        )
        self.assertAlmostEqual(measured, mirrored)
        self.assertGreater(measured, 0.0)
        self.assertLessEqual(measured, float(np.hypot(*(end - start))))


if __name__ == "__main__":
    unittest.main()
