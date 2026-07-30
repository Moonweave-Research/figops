import json
import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from hub_core.geometry_artist_overlaps import (  # noqa: E402
    _line_text_crossings,
    _segment_bbox_intersection_length,
)
from hub_core.geometry_diagnostics import (
    _is_paintable,  # noqa: E402
    diagnose_figure_geometry,  # noqa: E402
)


class Issue230GeometryTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_thin_line_crossing_is_available_in_raw_v2_without_changing_legacy_artist_overlap(self):
        fig, ax = plt.subplots(figsize=(8, 2))
        # Only the final few pixels enter the text bbox.  The padded line AABB
        # therefore stays below the legacy relative-overlap cutoff while the
        # centerline crossing remains a real, positive-length fact.
        ax.plot([0.1, 0.49], [0.5, 0.5], linewidth=0.5)
        ax.text(0.5, 0.5, "on line", ha="center", va="center")
        fig.canvas.draw()

        legacy = diagnose_figure_geometry(fig, [ax], layout_locked=False)
        artist_check = next(item for item in legacy["checks"] if item["name"] == "artist_overlaps")
        self.assertTrue(artist_check["passed"])
        self.assertEqual(artist_check["data"]["overlaps"], [])
        self.assertNotIn("line_text_crossings", artist_check["data"])

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"] if item["metric_id"] == "line_text_crossings[axis=0]"
        )
        self.assertEqual(measurement["availability"], "available")
        self.assertEqual(measurement["value"]["crossing_count"], 1)
        self.assertEqual(measurement["value"]["reported_crossing_count"], 1)
        self.assertEqual(measurement["value"]["crossings"][0]["line"], "line:0")
        self.assertTrue(measurement["value"]["crossings"][0]["text"].startswith("text:"))
        self.assertNotIn("threshold", json.dumps(measurement))
        self.assertNotIn("passed", json.dumps(measurement))

    def test_bbox_clipping_rejects_edge_contact_and_short_numerical_touch(self):
        box = Bbox.from_extents(10, 10, 20, 20)
        self.assertEqual(
            _segment_bbox_intersection_length(np.array((0.0, 0.0)), np.array((10.0, 10.0)), box),
            0.0,
        )
        self.assertEqual(
            _segment_bbox_intersection_length(np.array((0.0, 15.0)), np.array((10.5, 15.0)), box),
            0.0,
        )
        self.assertAlmostEqual(
            _segment_bbox_intersection_length(np.array((0.0, 15.0)), np.array((30.0, 15.0)), box),
            10.0,
        )

    def test_nan_separated_paths_do_not_join_across_gap(self):
        fig, ax = plt.subplots()
        ax.plot([0.1, 0.4, np.nan, 0.6, 0.9], [0.5, 0.5, np.nan, 0.5, 0.5])
        ax.text(0.5, 0.5, "gap", ha="center", va="center")
        fig.canvas.draw()

        facts = _line_text_crossings(
            ax,
            fig.canvas.get_renderer(),
            is_paintable=_is_paintable,
            candidate_cap=200,
            reported_cap=50,
        )
        self.assertEqual(facts["crossing_count"], 0)

    def test_reference_lines_use_their_blended_transform_with_nondefault_limits(self):
        for reference_kind in ("h", "v"):
            with self.subTest(reference_kind=reference_kind):
                fig, ax = plt.subplots()
                ax.set_xlim(10, 20)
                ax.set_ylim(100, 200)
                if reference_kind == "h":
                    ax.axhline(150, linewidth=0.5)
                else:
                    ax.axvline(15, linewidth=0.5)
                ax.text(15, 150, "reference", ha="center", va="center")
                fig.canvas.draw()

                facts = _line_text_crossings(
                    ax,
                    fig.canvas.get_renderer(),
                    is_paintable=_is_paintable,
                    candidate_cap=200,
                    reported_cap=50,
                )
                self.assertEqual(facts["crossing_count"], 1)

    def test_crossings_are_stable_and_bounded_by_caps(self):
        fig, ax = plt.subplots()
        for y in (0.3, 0.5, 0.7):
            ax.plot([0.1, 0.9], [y, y])
        for y in (0.3, 0.5, 0.7):
            ax.text(0.5, y, f"line-{y}", ha="center", va="center")
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()

        first = _line_text_crossings(
            ax,
            renderer,
            is_paintable=_is_paintable,
            candidate_cap=2,
            reported_cap=1,
        )
        second = _line_text_crossings(
            ax,
            renderer,
            is_paintable=_is_paintable,
            candidate_cap=2,
            reported_cap=1,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["line_count"], 3)
        self.assertEqual(first["evaluated_line_count"], 2)
        self.assertTrue(first["lines_truncated"])
        self.assertEqual(first["text_count"], 3)
        self.assertEqual(first["evaluated_text_count"], 2)
        self.assertTrue(first["texts_truncated"])
        self.assertLessEqual(first["reported_crossing_count"], 1)
        self.assertTrue(first["crossings_truncated"])
        json.dumps(first)

    def test_invisible_text_is_not_a_crossing_candidate(self):
        fig, ax = plt.subplots()
        ax.plot([0.1, 0.9], [0.5, 0.5])
        text = ax.text(0.5, 0.5, "hidden", ha="center", va="center")
        text.set_alpha(0.0)
        fig.canvas.draw()

        facts = _line_text_crossings(
            ax,
            fig.canvas.get_renderer(),
            is_paintable=_is_paintable,
            candidate_cap=200,
            reported_cap=50,
        )
        self.assertEqual(facts["text_count"], 0)
        self.assertEqual(facts["crossing_count"], 0)


if __name__ == "__main__":
    unittest.main()
