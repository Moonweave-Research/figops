import json
import os
import time
import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from hub_core.geometry_diagnostics import (  # noqa: E402
    GEOM_EPS_PX,
    MAX_TEXT_ARTISTS,
    SCHEMA_VERSION,
    _box_area,
    _inter_area,
    diagnose_figure_geometry,
)
from themes.journal_theme import _safe_geometry_diagnostics_inline  # noqa: E402


def _drawn(fig):
    fig.canvas.draw()
    return fig


def _check(result, name):
    matches = [c for c in result["checks"] if c["name"] == name]
    assert matches, f"no check named {name}"
    return matches[0]


def _find_non_native(value, path="root"):
    if isinstance(value, np.generic):
        return f"{path} ({type(value).__name__})"
    if isinstance(value, tuple):
        return f"{path} (tuple)"
    if isinstance(value, dict):
        for key, sub in value.items():
            found = _find_non_native(sub, f"{path}.{key}")
            if found:
                return found
    if isinstance(value, list):
        for index, sub in enumerate(value):
            found = _find_non_native(sub, f"{path}[{index}]")
            if found:
                return found
    return None


class GeometryDiagnosticsUnitTest(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_contract_shape_and_version(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 2])
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        self.assertEqual(set(result), {"schema_version", "passed", "checks", "warnings"})
        self.assertEqual(result["schema_version"], "geometry_diagnostics/1")
        self.assertEqual(SCHEMA_VERSION, "geometry_diagnostics/1")
        for check in result["checks"]:
            self.assertEqual({"name", "passed", "detail", "data"}, set(check))
        warning_eligible = {
            "tick_label_overlaps",
            "tick_label_crowding",
            "artists_outside_axes",
            "artists_outside_figure",
            "axis_label_title_overlap",
            "colorbar_overlap",
            "point_annotation_overlaps",
            "artist_overlaps",
            "legend_internal_overlaps",
            "marker_marker_overlaps",
            "text_axis_edge_proximity",
            "label_offset_consistency",
            "font_size_token_drift",
        }
        expected = all(c["passed"] for c in result["checks"] if c["name"] in warning_eligible)
        self.assertEqual(result["passed"], expected)

    def test_json_post_condition_native_types(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [3, 1, 2], label="series")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_title("title")
        ax.legend()
        ax.scatter([1.0], [1.0], s=300)
        ax.annotate("p", (1.0, 1.0))
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=True)
        # No default= allowed: a leaked numpy scalar/tuple would raise here.
        json.dumps(result)
        self.assertIsNone(_find_non_native(result))
        overlaps = _check(result, "tick_label_overlaps")["data"]["x_overlap_pairs"]
        for pair in overlaps:
            self.assertIsInstance(pair, list)
            self.assertTrue(all(isinstance(index, int) for index in pair))

    def test_overlap_positive_unrotated(self):
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.bar(range(8), range(8))
        ax.set_xticks(range(8))
        ax.set_xticklabels([f"category-label-{i}" for i in range(8)], rotation=0)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "tick_label_overlaps")
        self.assertFalse(check["passed"])
        self.assertTrue(check["data"]["x_overlap_pairs"])

    def test_boundary_is_font_free(self):
        non_overlap_a = Bbox.from_extents(0.0, 0.0, 10.0, 10.0)
        non_overlap_b = Bbox.from_extents(20.0, 20.0, 30.0, 30.0)
        self.assertEqual(_inter_area(non_overlap_a, non_overlap_b), 0.0)
        edge_a = Bbox.from_extents(0.0, 0.0, 10.0, 10.0)
        edge_b = Bbox.from_extents(10.0, 0.0, 20.0, 10.0)
        self.assertEqual(_inter_area(edge_a, edge_b), 0.0)
        # sub-pixel AREA overlap (0.5*0.5=0.25 < GEOM_EPS_PX**2=1.0) must not fire
        tiny_a = Bbox.from_extents(0.0, 0.0, 10.0, 10.0)
        tiny_b = Bbox.from_extents(10.0 - 0.5, 10.0 - 0.5, 20.0, 20.0)
        self.assertEqual(_inter_area(tiny_a, tiny_b), 0.0)
        over_a = Bbox.from_extents(0.0, 0.0, 10.0, 10.0)
        over_b = Bbox.from_extents(5.0, 0.0, 20.0, 10.0)
        self.assertGreater(_inter_area(over_a, over_b), GEOM_EPS_PX**2)

    def test_rotated_labels_not_tripped(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(range(8), range(8))
        ax.set_xticks(range(8))
        ax.set_xticklabels([f"cat{i}" for i in range(8)], rotation=45)
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        self.assertTrue(_check(result, "tick_label_overlaps")["passed"])
        self.assertTrue(_check(result, "tick_label_crowding")["passed"])

    def test_outside_axes_gating(self):
        # (a) explicit limits tighter than data -> skip
        fig_a, ax_a = plt.subplots()
        ax_a.plot([0, 10], [0, 10])
        ax_a.set_xlim(2, 4)
        ax_a.set_ylim(2, 4)
        check_a = _check(diagnose_figure_geometry(_drawn(fig_a), [ax_a], layout_locked=False), "artists_outside_axes")
        self.assertTrue(check_a["passed"])
        self.assertTrue(check_a["detail"].startswith("skipped: explicit limits"))

        # (b) autoscale on + genuine overflow
        fig_b, ax_b = plt.subplots()
        ax_b.plot([0, 1], [0, 1])
        ax_b.set_xlim(0, 0.25)  # leave y autoscaled, force x overflow
        check_b = _check(diagnose_figure_geometry(_drawn(fig_b), [ax_b], layout_locked=False), "artists_outside_axes")
        self.assertFalse(check_b["passed"])

        # (c) bare subplots -> no data artists
        fig_c, ax_c = plt.subplots()
        check_c = _check(diagnose_figure_geometry(_drawn(fig_c), [ax_c], layout_locked=False), "artists_outside_axes")
        self.assertTrue(check_c["passed"])
        self.assertTrue(check_c["detail"].startswith("skipped: no data artists"))

    def test_visibility_alpha_filter(self):
        # A hidden/transparent artist far outside the view must NOT inflate the data
        # extent: with the view pinned to the visible data, the outside fraction stays 0.
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 2])
        ax.plot([0, 100], [0, 100], alpha=0.0)
        (hidden,) = ax.plot([0, 100], [0, 100])
        hidden.set_visible(False)
        ax.set_xlim(0, 2)
        ax.set_ylim(0, 2)
        ax.set_autoscalex_on(True)  # keep the autoscale gate active despite the pinned view
        ax.set_autoscaley_on(True)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artists_outside_axes")
        self.assertTrue(check["passed"])
        self.assertLessEqual(check["data"]["outside_fraction"], 0.01)

    def test_annotation_marker_footprint(self):
        fig, ax = plt.subplots()
        ax.scatter([0.5], [0.5], s=200)
        ax.annotate("p", (0.5, 0.5))
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "point_annotation_overlaps")
        self.assertFalse(check["passed"])

    def test_artist_overlaps_reports_text_marker_pairs(self):
        fig, ax = plt.subplots()
        ax.scatter([0.5], [0.5], s=300)
        ax.text(0.5, 0.5, "S70", ha="center", va="center")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(any(item["a"].startswith("text:") or item["b"].startswith("text:") for item in check["data"]["overlaps"]))
        self.assertTrue(any("marker:" in item["a"] or "marker:" in item["b"] for item in check["data"]["overlaps"]))

    def test_artist_overlaps_reports_text_title_pairs(self):
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.set_title("(c) panel title")
        ax.text(0.5, 1.02, "controls (ref.)", ha="center", va="bottom", transform=ax.transAxes)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(any("controls" in item["a"] or "controls" in item["b"] for item in check["data"]["overlaps"]))
        self.assertTrue(any("title:" in item["a"] or "title:" in item["b"] for item in check["data"]["overlaps"]))

    def test_artist_overlaps_uses_individual_marker_boxes_not_collection_union(self):
        fig, ax = plt.subplots()
        ax.scatter([0.0, 1.0], [0.0, 1.0], s=40)
        ax.text(0.5, 0.5, "between markers", ha="center", va="center")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["overlaps"], [])

    def test_legend_internal_overlaps_reports_packed_handles(self):
        fig, ax = plt.subplots(figsize=(2, 2))
        handles = [
            Line2D([0], [0], marker=marker, linestyle="", markersize=14, label=label)
            for marker, label in (("o", "circle"), ("D", "diamond"), ("s", "square"))
        ]
        ax.legend(handles=handles, labels=["circle", "diamond", "square"], labelspacing=-0.2, loc="center")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_internal_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(any(item["kind"] == "handle_handle" for item in check["data"]["overlaps"]))

    def test_marker_marker_overlaps_reports_iou_severity(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter([0.50, 0.505], [0.50, 0.50], s=900)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "marker_marker_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(check["data"]["overlaps"])
        self.assertIn(check["data"]["overlaps"][0]["severity"], {"low", "medium", "high"})
        self.assertGreater(check["data"]["overlaps"][0]["iou"], 0)

    def test_label_offset_consistency_warns_for_repeated_label_direction_change(self):
        fig, axes = plt.subplots(1, 3, figsize=(6, 2))
        for ax in axes:
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.scatter([0.5], [0.5], s=80)
        axes[0].text(0.62, 0.5, "PDMS", ha="left", va="center")
        axes[1].text(0.62, 0.5, "PDMS", ha="left", va="center")
        axes[2].text(0.5, 0.38, "PDMS", ha="center", va="top")
        check = _check(diagnose_figure_geometry(_drawn(fig), list(axes), layout_locked=False), "label_offset_consistency")

        self.assertFalse(check["passed"])
        inconsistency = check["data"]["inconsistencies"][0]
        self.assertEqual(inconsistency["label"], "PDMS")
        self.assertEqual(set(inconsistency["directions"]), {"below", "right"})

    def test_text_axis_edge_proximity_reports_clipped_label(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(0.5, -0.02, "PDMS", ha="center", va="top")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "text_axis_edge_proximity")

        self.assertFalse(check["passed"])
        finding = check["data"]["findings"][0]
        self.assertEqual(finding["artist"], "text:'PDMS'")
        self.assertIn("bottom", finding["edges"])
        self.assertTrue(finding["clipped"])

    def test_font_size_token_drift_reports_raw_non_token_sizes(self):
        fig, ax = plt.subplots()
        ax.text(0.2, 0.2, "S70", fontsize=5)
        ax.text(0.4, 0.4, "PET", fontsize=6)
        ax.text(0.6, 0.6, "drift", fontsize=5.5)
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False, font_token_sizes=[5, 6, 7])
        check = _check(result, "font_size_token_drift")

        self.assertFalse(check["passed"])
        self.assertEqual(check["data"]["offenders"][0]["text"], "drift")
        self.assertEqual(check["data"]["offenders"][0]["fontsize"], 5.5)

    def test_annotation_cap(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        for index in range(MAX_TEXT_ARTISTS + 1):
            ax.annotate(str(index), (index / 500, index / 500))
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "point_annotation_overlaps")
        self.assertTrue(check["passed"])
        self.assertTrue(check["detail"].startswith("skipped: annotation count"))

    def test_mode_sensitivity_outside_figure(self):
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.plot([0, 1], [0, 1])
        ax.set_ylabel("a very long axis label that pushes the chrome past the canvas edge clearly")
        ax.set_title("an equally long figure title forcing the chrome outside the bbox edge")
        drawn = _drawn(fig)
        locked = _check(diagnose_figure_geometry(drawn, [ax], layout_locked=True), "artists_outside_figure")
        unlocked = _check(diagnose_figure_geometry(drawn, [ax], layout_locked=False), "artists_outside_figure")
        self.assertTrue(unlocked["passed"])
        self.assertEqual(unlocked["detail"], "figure overflow absorbed by tight bbox")
        self.assertGreater(locked["data"]["overflow_count"], 0)
        self.assertFalse(locked["passed"])

    def test_colorbar_classification(self):
        # twinx is not a colorbar
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        ax.twinx().plot([0, 1], [1, 0])
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        self.assertTrue(_check(result, "colorbar_overlap")["passed"])
        self.assertTrue(_check(result, "colorbar_overlap")["detail"].startswith("skipped: no tagged colorbar"))

        # tagged colorbar IS inspected
        fig2, ax2 = plt.subplots()
        mesh = ax2.pcolormesh(np.arange(3), np.arange(3), np.random.rand(2, 2))
        colorbar = fig2.colorbar(mesh, ax=ax2)
        colorbar.ax._graph_hub_role = "colorbar"
        check2 = _check(diagnose_figure_geometry(_drawn(fig2), [ax2], layout_locked=False), "colorbar_overlap")
        self.assertNotIn("skipped", check2["detail"])

    def test_colorbar_overlap_uses_smaller_box_denominator(self):
        # §2.0 mandates overlap_frac = inter / min(panel.area, cbar.area). A thin colorbar
        # strip poking into a panel intrudes ~12% of its OWN area but only ~0.6% of the panel
        # area. Dividing by the panel (the bug) keeps it under 0.02 and never warns; dividing
        # by the smaller box correctly trips the warning.
        fig = plt.figure(figsize=(6, 4))
        ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
        ax.plot([0, 1], [0, 1])
        cax = fig.add_axes([0.895, 0.1, 0.04, 0.8])
        cax._graph_hub_role = "colorbar"
        _drawn(fig)
        renderer = fig.canvas.get_renderer()
        panel_bb = ax.get_window_extent(renderer)
        cbar_bb = cax.get_window_extent(renderer)
        inter = _inter_area(panel_bb, cbar_bb)
        frac_by_panel = inter / _box_area(panel_bb)
        frac_by_min = inter / min(_box_area(panel_bb), _box_area(cbar_bb))
        # Guard: the panel-area denominator (the bug) would NOT fire; the smaller-box one does.
        self.assertLess(frac_by_panel, 0.02)
        self.assertGreater(frac_by_min, 0.02)
        check = _check(diagnose_figure_geometry(fig, [ax], layout_locked=False), "colorbar_overlap")
        self.assertFalse(check["passed"])

    def test_info_only_neutrality(self):
        fig, ax = plt.subplots()
        ax.scatter([0, 0, 1, 1], [0, 1, 0, 1], s=400, label="d")
        leg = ax.legend(loc="center")
        # force legend over the data center
        self.assertIsNotNone(leg)
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        legend_check = _check(result, "legend_data_collision")
        blank_check = _check(result, "blank_area_ratio")
        # The legend sits over the data center: a real overlap is measured, yet info-only
        # never flips status (and never enters the aggregate).
        self.assertGreater(legend_check["data"]["overlap_frac"], 0)
        self.assertTrue(legend_check["passed"])
        self.assertTrue(blank_check["passed"])

    def test_raises_on_bad_input_not_findings(self):
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.bar(range(8), range(8))
        ax.set_xticks(range(8))
        ax.set_xticklabels([f"category-label-{i}" for i in range(8)], rotation=0)
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        self.assertIsInstance(result, dict)
        self.assertFalse(result["passed"])
        with self.assertRaises(ValueError):
            diagnose_figure_geometry(fig, [], layout_locked=False)

    def test_budget_skip_fixed_floor(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 2])
        _drawn(fig)
        prior = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
        prior_timeout = os.environ.pop("MCP_RENDER_TIMEOUT_SECONDS", None)
        try:
            # (a) deadline inside the 5 s floor -> skip
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 2.0)
            skipped = _safe_geometry_diagnostics_inline(fig)
            self.assertIsNone(skipped["passed"])
            self.assertEqual(skipped["warnings"], ["skipped: render budget"])
            self.assertEqual(skipped["checks"], [])

            # (b) generous deadline -> measurement runs
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 3600)
            measured = _safe_geometry_diagnostics_inline(fig)
            self.assertIsInstance(measured["passed"], bool)
            self.assertTrue(measured["checks"])

            # (c) MCP_RENDER_TIMEOUT_SECONDS absent does not change either decision
            self.assertNotIn("MCP_RENDER_TIMEOUT_SECONDS", os.environ)
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 2.0)
            self.assertIsNone(_safe_geometry_diagnostics_inline(fig)["passed"])
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 3600)
            self.assertIsInstance(_safe_geometry_diagnostics_inline(fig)["passed"], bool)
        finally:
            if prior is None:
                os.environ.pop("GEOMETRY_DIAGNOSTICS_DEADLINE", None)
            else:
                os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = prior
            if prior_timeout is not None:
                os.environ["MCP_RENDER_TIMEOUT_SECONDS"] = prior_timeout


if __name__ == "__main__":
    unittest.main()
