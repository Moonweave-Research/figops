import hashlib
import json
import os
import time
import unittest
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from hub_core import (  # noqa: E402
    geometry_artist_overlaps,
    geometry_bounds_checks,
    geometry_diagnostics,
    geometry_label_offsets,
    geometry_layout_checks,
    geometry_marker_styles,
    geometry_overlay_contrast,
    geometry_primitives,
    geometry_style_checks,
    geometry_tick_labels,
)
from hub_core.geometry_diagnostics import (  # noqa: E402
    GEOM_EPS_PX,
    MAX_TEXT_ARTISTS,
    SCHEMA_VERSION,
    _box_area,
    _box_vector_away,
    _inter_area,
    _marker_footprint_box_entries,
    diagnose_figure_geometry,
)
from hub_core.geometry_raw_contract import (  # noqa: E402
    RawGeometryContractError,
    normalize_geometry_payload,
    raw_measurement,
    validate_raw_geometry,
)
from hub_core.mcp.render_geometry_schemas import GEOMETRY_METRIC_NAMES  # noqa: E402
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


def _candidate_signature(candidates):
    return [(label, tuple(round(float(value), 6) for value in box.bounds)) for label, box in candidates]


def _bbox_signature(box):
    if box is None:
        return None
    return tuple(round(float(value), 6) for value in box.bounds)


class GeometryDiagnosticsUnitTest(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_raw_contract_rejects_recursive_policy_and_aggregate_fields(self):
        base = {
            "schema_version": "geometry_diagnostics/2",
            "measurements": [
                {
                    "metric_id": "geometry.fact",
                    "availability": "available",
                    "value": {"count": 1},
                    "unit": "count",
                    "scope": "figure",
                }
            ],
            "warnings": [],
        }
        for field in (
            "threshold",
            "severity",
            "verdict",
            "aggregate",
            "nested_policy_id",
            "min_distance",
            "max_distance",
            "limit",
            "offender_count",
            "passed",
            "failed",
        ):
            with self.subTest(field=field):
                payload = json.loads(json.dumps(base))
                payload["measurements"][0]["value"] = {"nested": [{field: 1}]}
                with self.assertRaisesRegex(RawGeometryContractError, "policy-owned field"):
                    validate_raw_geometry(payload)

    def test_raw_contract_enforces_availability_value_reason_discriminator(self):
        common = {"metric_id": "geometry.fact", "unit": "count", "scope": "figure"}
        invalid = (
            {**common, "availability": "available", "reason": "not measured"},
            {**common, "availability": "available", "value": 1, "reason": "conflict"},
            {**common, "availability": "unavailable"},
            {**common, "availability": "unavailable", "value": 1, "reason": "conflict"},
        )
        for measurement in invalid:
            with self.subTest(measurement=measurement):
                with self.assertRaises(RawGeometryContractError):
                    validate_raw_geometry(
                        {
                            "schema_version": "geometry_diagnostics/2",
                            "measurements": [measurement],
                            "warnings": [],
                        }
                    )

    def test_legacy_geometry_is_normalized_only_through_compatibility_adapter(self):
        normalized = normalize_geometry_payload(
            {
                "schema_version": "geometry_diagnostics/1",
                "passed": False,
                "checks": [
                    {
                        "name": "tick_label_overlaps",
                        "passed": False,
                        "detail": "one pair",
                        "data": {"axis_index": 0, "pairs": [[0, 1]], "threshold": 0},
                    }
                ],
                "warnings": ["legacy"],
            }
        )
        self.assertEqual(normalized["schema_version"], "geometry_diagnostics/2")
        self.assertEqual(normalized["measurements"][0]["value"], {"axis_index": 0, "pairs": [[0, 1]]})
        self.assertEqual(normalized["measurements"][0]["availability"], "available")
        self.assertNotIn("passed", normalized)

    def test_failed_legacy_outcome_cannot_make_computed_raw_fact_unavailable(self):
        measurement = raw_measurement(
            {
                "name": "objective_ratio",
                "passed": False,
                "detail": "outside selected policy",
                "data": {"ratio": 0.5},
            },
            0,
        )
        self.assertEqual(measurement["availability"], "available")
        self.assertEqual(measurement["value"], {"ratio": 0.5})

    def test_explicit_xlim_preserves_computed_outside_fraction_as_available(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0.0, 2.0], [0.0, 1.0])
        ax.set_xlim(0.0, 1.0)
        _drawn(fig)

        legacy = diagnose_figure_geometry(fig, [ax], layout_locked=True)
        legacy_check = _check(legacy, "artists_outside_axes")
        self.assertIsNone(legacy_check["passed"])
        self.assertAlmostEqual(legacy_check["data"]["outside_fraction"], 0.5)

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=True, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"]
            if item["metric_id"] == "artists_outside_axes[axis=0]"
        )
        self.assertEqual(measurement["availability"], "available")
        self.assertAlmostEqual(measurement["value"]["outside_fraction"], 0.5)

    def test_legacy_adapter_preserves_axis_scope_for_repeated_metric_names(self):
        normalized = normalize_geometry_payload(
            {
                "schema_version": "geometry_diagnostics/1",
                "passed": True,
                "checks": [
                    {
                        "name": "blank_area_ratio",
                        "passed": True,
                        "detail": "measured",
                        "data": {"axis_index": axis_index, "blank_ratio": 0.25},
                    }
                    for axis_index in (0, 1)
                ],
                "warnings": [],
            }
        )
        self.assertEqual(
            [item["metric_id"] for item in normalized["measurements"]],
            ["blank_area_ratio[axis=0]", "blank_area_ratio[axis=1]"],
        )

    def test_raw_edge_distances_retain_near_and_far_candidates(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.text(0.0, 0.8, "near", transform=ax.transAxes)
        ax.text(0.5, 0.6, "far", transform=ax.transAxes)
        _drawn(fig)

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=True, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"]
            if item["metric_id"] == "text_axis_edge_distances[axis=0]"
        )
        left_distances = [item["distances_px"]["left"] for item in measurement["value"]["artists"]]
        self.assertTrue(any(distance <= 3.0 for distance in left_distances))
        self.assertTrue(any(distance > 3.0 for distance in left_distances))
        self.assertNotIn("threshold", json.dumps(measurement))

    def test_raw_discovery_metric_families_exactly_match_runtime_output(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([0, 1], [0, 1])
        ax.text(0.5, 0.5, "fact", transform=ax.transAxes)
        _drawn(fig)

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=True, contract_version="raw")
        runtime_families = {item["metric_id"].split("[", 1)[0] for item in raw["measurements"]}
        self.assertEqual(runtime_families, set(GEOMETRY_METRIC_NAMES))

    def test_raw_artist_iou_retains_below_and_above_old_warn_cutoff(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.text(0.1, 0.7, "high-a", transform=ax.transAxes)
        ax.text(0.1, 0.7, "high-b", transform=ax.transAxes)
        low_a = ax.text(0.1, 0.4, "low-a", transform=ax.transAxes)
        _drawn(fig)
        low_a_box = low_a.get_window_extent(fig.canvas.get_renderer())
        low_b_x = ax.transAxes.inverted().transform((low_a_box.x1 - 0.5, low_a_box.y0))[0]
        ax.text(low_b_x, 0.4, "low-b", transform=ax.transAxes)
        _drawn(fig)

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=True, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"]
            if item["metric_id"] == "artist_pair_iou[axis=0]"
        )
        positive = [pair["iou"] for pair in measurement["value"]["pairs"] if pair["iou"] > 0]
        self.assertTrue(any(0 < iou <= 0.05 for iou in positive), positive)
        self.assertTrue(any(iou > 0.05 for iou in positive), positive)
        self.assertIn("pairs_truncated", measurement["value"])

    def test_raw_contrast_retains_below_and_above_old_warn_cutoff(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        for x, color, label in ((0.05, "black", "low"), (0.55, "white", "high")):
            overlay = Rectangle(
                (x, 0.35), 0.35, 0.2, transform=ax.transAxes, facecolor=color, edgecolor="none"
            )
            overlay._graph_hub_overlay_role = "evidence-band"
            overlay._graph_hub_overlay_label = label
            ax.add_patch(overlay)
            text = ax.text(x + 0.03, 0.42, label, color="black", transform=ax.transAxes)
            text._graph_hub_annotation_text_role = "claim"
        _drawn(fig)

        raw = diagnose_figure_geometry(fig, [ax], layout_locked=True, contract_version="raw")
        measurement = next(
            item for item in raw["measurements"]
            if item["metric_id"] == "annotation_overlay_contrast_ratios[axis=0]"
        )
        ratios = [pair["contrast_ratio"] for pair in measurement["value"]["pairs"]]
        self.assertTrue(any(ratio < 3.0 for ratio in ratios), ratios)
        self.assertTrue(any(ratio >= 3.0 for ratio in ratios), ratios)
        self.assertNotIn("threshold", json.dumps(measurement))

    def test_geometry_diagnostics_keeps_primitive_compatibility_exports(self):
        self.assertIs(geometry_diagnostics._extent, geometry_primitives._extent)
        self.assertIs(geometry_diagnostics._inter_area, geometry_primitives._inter_area)
        self.assertIs(geometry_diagnostics._boxes_overlap, geometry_primitives._boxes_overlap)
        self.assertIs(geometry_diagnostics._box_area, geometry_primitives._box_area)
        self.assertIs(geometry_diagnostics._overlap_fraction, geometry_primitives._overlap_fraction)
        self.assertIs(geometry_diagnostics._circle_overlap_fraction, geometry_primitives._circle_overlap_fraction)
        self.assertIs(geometry_diagnostics._overlap_severity, geometry_primitives._overlap_severity)

    def test_geometry_diagnostics_keeps_marker_style_compatibility_exports(self):
        self.assertIs(geometry_diagnostics._is_none_color, geometry_marker_styles._is_none_color)
        self.assertIs(geometry_diagnostics._rgba_tuple, geometry_marker_styles._rgba_tuple)
        self.assertIs(geometry_diagnostics._style_color, geometry_marker_styles._style_color)
        self.assertIs(geometry_diagnostics._path_signature, geometry_marker_styles._path_signature)
        self.assertIs(geometry_diagnostics._line_marker_style, geometry_marker_styles._line_marker_style)
        self.assertIs(geometry_diagnostics._collection_marker_style, geometry_marker_styles._collection_marker_style)
        self.assertIs(geometry_diagnostics._marker_style, geometry_marker_styles._marker_style)
        self.assertIs(geometry_diagnostics._style_diff, geometry_marker_styles._style_diff)

    def test_marker_footprint_facade_preserves_paintability_patch_surface(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.scatter([0.5], [0.5], s=100)
        _drawn(fig)

        self.assertEqual(len(_marker_footprint_box_entries(ax, fig)), 1)
        with patch.object(geometry_diagnostics, "_collection_marker_is_paintable", return_value=False):
            self.assertEqual(_marker_footprint_box_entries(ax, fig), [])

    def test_geometry_diagnostics_keeps_style_check_compatibility_exports(self):
        self.assertIs(geometry_diagnostics._default_font_token_sizes, geometry_style_checks._default_font_token_sizes)
        self.assertIs(geometry_diagnostics._font_size_matches_token, geometry_style_checks._font_size_matches_token)
        self.assertIs(geometry_diagnostics._font_size_token_drift, geometry_style_checks._font_size_token_drift)
        self.assertIs(geometry_diagnostics._journal_compliance, geometry_style_checks._journal_compliance)
        self.assertIs(geometry_diagnostics._journal_font_offenders, geometry_style_checks._journal_font_offenders)
        self.assertIs(geometry_diagnostics._journal_line_offenders, geometry_style_checks._journal_line_offenders)
        self.assertIs(geometry_diagnostics._line_width_values, geometry_style_checks._line_width_values)
        self.assertIs(geometry_diagnostics._append_linewidth_offender, geometry_style_checks._append_linewidth_offender)

    def test_geometry_diagnostics_keeps_overlay_contrast_compatibility_exports(self):
        self.assertIs(
            geometry_diagnostics._annotation_overlay_contrast,
            geometry_overlay_contrast._annotation_overlay_contrast,
        )
        self.assertIs(geometry_diagnostics._overlay_contrast_items, geometry_overlay_contrast._overlay_contrast_items)
        self.assertIs(geometry_diagnostics._overlay_artist_rgb, geometry_overlay_contrast._overlay_artist_rgb)
        self.assertIs(geometry_diagnostics._artist_rgb, geometry_overlay_contrast._artist_rgb)
        self.assertIs(geometry_diagnostics._composite_rgb, geometry_overlay_contrast._composite_rgb)
        self.assertIs(geometry_diagnostics._relative_luminance, geometry_overlay_contrast._relative_luminance)
        self.assertIs(geometry_diagnostics._contrast_ratio, geometry_overlay_contrast._contrast_ratio)

    def test_geometry_diagnostics_keeps_label_offset_compatibility_exports(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter([0.5], [0.5], s=80)
        text = ax.text(0.62, 0.5, "PDMS", ha="left", va="center")
        _drawn(fig)

        self.assertEqual(geometry_diagnostics._nearest_marker_direction(ax, text, fig.canvas.get_renderer()), "right")
        direct = geometry_label_offsets._label_offset_consistency(
            fig,
            [ax],
            fig.canvas.get_renderer(),
            marker_footprint_box_entries=geometry_diagnostics._marker_footprint_box_entries,
            is_paintable=geometry_diagnostics._is_paintable,
            max_reported_pairs=50,
        )
        compat = geometry_diagnostics._label_offset_consistency(fig, [ax], fig.canvas.get_renderer())
        self.assertEqual(compat, direct)
        self.assertIs(geometry_diagnostics._point_label_skips, geometry_label_offsets._point_label_skips)
        edge_direct = geometry_label_offsets._text_axis_edge_proximity(
            ax,
            fig.canvas.get_renderer(),
            0,
            is_paintable=geometry_diagnostics._is_paintable,
            threshold_px=geometry_diagnostics.TEXT_AXIS_EDGE_WARN_PX,
            max_reported_pairs=50,
        )
        edge_compat = geometry_diagnostics._text_axis_edge_proximity(ax, fig.canvas.get_renderer(), 0)
        self.assertEqual(edge_compat, edge_direct)

    def test_geometry_diagnostics_keeps_layout_check_compatibility_exports(self):
        fig, ax = plt.subplots(figsize=(3, 2))
        ax.set_title("Panel")
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        fig.suptitle("Figure")
        _drawn(fig)
        renderer = fig.canvas.get_renderer()

        axis_direct = geometry_layout_checks._axis_label_title_overlap(
            ax,
            renderer,
            0,
            is_paintable=geometry_diagnostics._is_paintable,
        )
        self.assertEqual(geometry_diagnostics._axis_label_title_overlap(ax, renderer, 0), axis_direct)
        figure_direct = geometry_layout_checks._figure_title_panel_title_overlap(
            fig,
            [ax],
            renderer,
            is_paintable=geometry_diagnostics._is_paintable,
        )
        self.assertEqual(geometry_diagnostics._figure_title_panel_title_overlap(fig, [ax], renderer), figure_direct)

    def test_geometry_diagnostics_keeps_artist_overlap_compatibility_exports(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.plot([0.2, 0.8], [0.5, 0.5], linewidth=2)
        ax.scatter([0.5], [0.5], s=80)
        ax.text(0.5, 0.5, "PDMS", ha="center", va="center")
        _drawn(fig)
        renderer = fig.canvas.get_renderer()

        self.assertIs(geometry_diagnostics._artist_label, geometry_artist_overlaps._artist_label)
        self.assertIs(geometry_diagnostics._line_overlap_boxes, geometry_artist_overlaps._line_overlap_boxes)
        self.assertIs(geometry_diagnostics._artist_candidate_kind, geometry_artist_overlaps._artist_candidate_kind)
        self.assertIs(
            geometry_diagnostics._is_reportable_artist_overlap,
            geometry_artist_overlaps._is_reportable_artist_overlap,
        )
        direct = geometry_artist_overlaps._artist_overlaps(
            ax,
            renderer,
            0,
            is_paintable=geometry_diagnostics._is_paintable,
            marker_footprint_box_entries=geometry_diagnostics._marker_footprint_box_entries,
            max_text_artists=geometry_diagnostics.MAX_TEXT_ARTISTS,
            artist_overlap_warn=geometry_diagnostics.ARTIST_OVERLAP_WARN,
            max_reported_pairs=50,
        )
        self.assertEqual(geometry_diagnostics._artist_overlaps(ax, renderer, 0), direct)
        candidate_direct = geometry_artist_overlaps._artist_overlap_candidates(
            ax,
            renderer,
            is_paintable=geometry_diagnostics._is_paintable,
            marker_footprint_box_entries=geometry_diagnostics._marker_footprint_box_entries,
        )
        self.assertEqual(
            _candidate_signature(geometry_diagnostics._artist_overlap_candidates(ax, renderer)),
            _candidate_signature(candidate_direct),
        )

    def test_geometry_diagnostics_keeps_tick_label_compatibility_exports(self):
        fig, ax = plt.subplots(figsize=(2.5, 2.5))
        labels = [f"long-label-{index}" for index in range(6)]
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=0)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["low", "high"])
        _drawn(fig)
        renderer = fig.canvas.get_renderer()
        visible_x = geometry_tick_labels._visible_tick_labels(
            list(ax.get_xticklabels()),
            is_paintable=geometry_diagnostics._is_paintable,
        )

        self.assertEqual(geometry_diagnostics._visible_tick_labels(list(ax.get_xticklabels())), visible_x)
        self.assertEqual(geometry_diagnostics._truncate_pairs([[0, 1]]), ([[0, 1]], False))
        self.assertEqual(
            geometry_diagnostics._axis_tick_overlaps(visible_x, renderer, "x"),
            geometry_tick_labels._axis_tick_overlaps(
                visible_x,
                renderer,
                "x",
                max_text_artists=geometry_diagnostics.MAX_TEXT_ARTISTS,
            ),
        )
        self.assertEqual(
            geometry_diagnostics._axis_crowding(visible_x, ax, renderer, "x"),
            geometry_tick_labels._axis_crowding(
                visible_x,
                ax,
                renderer,
                "x",
                max_text_artists=geometry_diagnostics.MAX_TEXT_ARTISTS,
            ),
        )
        direct_overlaps = geometry_tick_labels._tick_label_overlaps(
            ax,
            renderer,
            0,
            is_paintable=geometry_diagnostics._is_paintable,
            max_text_artists=geometry_diagnostics.MAX_TEXT_ARTISTS,
            max_reported_pairs=50,
        )
        self.assertEqual(geometry_diagnostics._tick_label_overlaps(ax, renderer, 0), direct_overlaps)
        direct_crowding = geometry_tick_labels._tick_label_crowding(
            ax,
            renderer,
            0,
            is_paintable=geometry_diagnostics._is_paintable,
            max_text_artists=geometry_diagnostics.MAX_TEXT_ARTISTS,
            tick_crowding_warn=geometry_diagnostics.TICK_CROWDING_WARN,
            crowding_near_low=geometry_diagnostics._CROWDING_NEAR_LOW,
            crowding_near_high=geometry_diagnostics._CROWDING_NEAR_HIGH,
        )
        self.assertEqual(geometry_diagnostics._tick_label_crowding(ax, renderer, 0), direct_crowding)

    def test_geometry_diagnostics_keeps_bounds_check_compatibility_exports(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.plot([0.0, 2.0], [0.0, 2.0])
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(0.0, 1.0)
        ax.set_title("Panel")
        ax.set_xlabel("X")
        _drawn(fig)
        renderer = fig.canvas.get_renderer()

        self.assertIs(geometry_diagnostics._overlap_fraction_1d, geometry_bounds_checks._overlap_fraction_1d)
        self.assertIs(
            geometry_diagnostics._degenerate_outside_fraction,
            geometry_bounds_checks._degenerate_outside_fraction,
        )
        self.assertEqual(
            len(geometry_diagnostics._visible_data_artists(ax)),
            len(geometry_bounds_checks._visible_data_artists(ax, is_paintable=geometry_diagnostics._is_paintable)),
        )
        self.assertEqual(
            _bbox_signature(geometry_diagnostics._visible_data_lim(ax)),
            _bbox_signature(
                geometry_bounds_checks._visible_data_lim(
                    ax,
                    is_paintable=geometry_diagnostics._is_paintable,
                )
            ),
        )
        outside_axes_direct = geometry_bounds_checks._artists_outside_axes(
            ax,
            renderer,
            0,
            is_paintable=geometry_diagnostics._is_paintable,
            data_outside_axes_warn=geometry_diagnostics.DATA_OUTSIDE_AXES_WARN,
        )
        self.assertEqual(geometry_diagnostics._artists_outside_axes(ax, renderer, 0), outside_axes_direct)
        self.assertEqual(
            len(geometry_diagnostics._chrome_artists(ax)),
            len(geometry_bounds_checks._chrome_artists(ax, is_paintable=geometry_diagnostics._is_paintable)),
        )
        outside_figure_direct = geometry_bounds_checks._artists_outside_figure(
            ax,
            fig,
            renderer,
            0,
            True,
            is_paintable=geometry_diagnostics._is_paintable,
        )
        self.assertEqual(
            geometry_diagnostics._artists_outside_figure(ax, fig, renderer, 0, True),
            outside_figure_direct,
        )

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
            "legend_marker_consistency",
            "label_offset_consistency",
            "point_label_skips",
            "annotation_overlay_contrast",
            "font_size_token_drift",
            "journal_compliance",
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
        # (a) explicit limits tighter than data -> informational crop report
        fig_a, ax_a = plt.subplots()
        ax_a.plot([0, 10], [0, 10])
        ax_a.set_xlim(2, 4)
        ax_a.set_ylim(2, 4)
        check_a = _check(diagnose_figure_geometry(_drawn(fig_a), [ax_a], layout_locked=False), "artists_outside_axes")
        self.assertIsNone(check_a["passed"])
        self.assertIn("explicit limits", check_a["detail"])
        self.assertGreater(check_a["data"]["outside_fraction"], 0.0)

        # (b) partial explicit limits also report the measured crop without failing open
        fig_b, ax_b = plt.subplots()
        ax_b.plot([0, 1], [0, 1])
        ax_b.set_xlim(0, 0.25)  # leave y autoscaled, force x overflow
        check_b = _check(diagnose_figure_geometry(_drawn(fig_b), [ax_b], layout_locked=False), "artists_outside_axes")
        self.assertIsNone(check_b["passed"])
        self.assertGreater(check_b["data"]["outside_fraction"], 0.0)

        # (c) bare subplots -> no data artists
        fig_c, ax_c = plt.subplots()
        check_c = _check(diagnose_figure_geometry(_drawn(fig_c), [ax_c], layout_locked=False), "artists_outside_axes")
        self.assertTrue(check_c["passed"])
        self.assertTrue(check_c["detail"].startswith("skipped: no data artists"))

    def test_outside_axes_reports_degenerate_line_extent(self):
        fig, ax = plt.subplots()
        ax.plot([2.0, 2.0], [0.0, 1.0])
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(0.0, 1.0)
        ax.set_autoscalex_on(True)
        ax.set_autoscaley_on(True)

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artists_outside_axes")

        self.assertFalse(check["passed"])
        self.assertGreater(check["data"]["outside_fraction"], 0.99)

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
        self.assertTrue(
            any(item["a"].startswith("text:") or item["b"].startswith("text:") for item in check["data"]["overlaps"])
        )
        self.assertTrue(any("marker:" in item["a"] or "marker:" in item["b"] for item in check["data"]["overlaps"]))

    def test_artist_overlaps_reports_stale_leader_metadata_label_on_marker_pair(self):
        fig, ax = plt.subplots()
        ax.scatter([0.5], [0.5], s=300)
        text = ax.text(0.5, 0.5, "S70", ha="center", va="center")
        text._graph_hub_leader_target_data = (0.5, 0.5)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(check["data"]["overlaps"])

    def test_artist_overlaps_reports_unmanaged_leader_metadata(self):
        fig, ax = plt.subplots()
        ax.set_xlim(0.45, 0.60)
        ax.set_ylim(0.45, 0.55)
        ax.scatter([0.5], [0.5], s=5000)
        text = ax.text(0.515, 0.5, "S70", ha="center", va="center")
        text._graph_hub_leader_target_data = (0.5, 0.5)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(check["data"]["overlaps"])

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

    def test_artist_overlaps_reports_text_line_pairs(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.plot([0.1, 0.9], [0.5, 0.5], linewidth=4.0)
        ax.text(0.5, 0.5, "on line", ha="center", va="center")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(any("line:" in item["a"] or "line:" in item["b"] for item in check["data"]["overlaps"]))

    def test_artist_overlaps_reports_text_patch_pairs(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.bar([0], [1], width=0.6)
        ax.text(0.0, 0.5, "on bar", ha="center", va="center")
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artist_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(any("patch:" in item["a"] or "patch:" in item["b"] for item in check["data"]["overlaps"]))

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

    def test_legend_internal_overlaps_ignores_empty_data_proxy_handle_extents(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        handles = [
            Line2D([], [], marker=marker, linestyle="none", markersize=8, label=label)
            for marker, label in (("o", "sulfur"), ("D", "trap-rich"), ("s", "control"))
        ]
        ax.legend(handles=handles, loc="lower right", labelspacing=1.0)
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_internal_overlaps")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["overlaps"], [])

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

    def test_marker_marker_overlaps_pass_for_separated_markers(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.scatter([0.2, 0.8], [0.2, 0.8], s=900)

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "marker_marker_overlaps")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["overlaps"], [])

    def test_dense_legible_scatter_does_not_report_spurious_overlap_clutter(self):
        fig, ax = plt.subplots(figsize=(3, 3), dpi=100)
        x = np.linspace(0.0, 1.0, 24)
        y = 0.5 + 0.08 * np.sin(np.linspace(0.0, 4.0 * np.pi, len(x)))
        ax.scatter(x, y, s=225)

        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        marker_check = _check(result, "marker_marker_overlaps")
        artist_check = _check(result, "artist_overlaps")

        self.assertTrue(marker_check["passed"])
        self.assertEqual(marker_check["data"]["overlaps"], [])
        self.assertTrue(artist_check["passed"])
        self.assertEqual(artist_check["data"]["overlaps"], [])

    def test_multiseries_errorbars_do_not_report_spurious_marker_or_artist_overlaps(self):
        fig, ax = plt.subplots(figsize=(4.8, 3.2), dpi=100)
        x = np.arange(8)
        for offset, phase in ((-0.12, 0.0), (0.0, 0.45), (0.12, 0.9)):
            y = 1.0 + 0.18 * np.sin(x * 0.7 + phase)
            ax.errorbar(x + offset, y, yerr=0.08, xerr=0.08, marker="o", markersize=6, capsize=4, linewidth=1.2)

        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        marker_check = _check(result, "marker_marker_overlaps")
        artist_check = _check(result, "artist_overlaps")

        self.assertTrue(marker_check["passed"])
        self.assertEqual(marker_check["data"]["overlaps"], [])
        self.assertTrue(artist_check["passed"])
        self.assertEqual(artist_check["data"]["overlaps"], [])

    def test_genuine_marker_marker_clutter_still_reports_overlap_fraction(self):
        fig, ax = plt.subplots(figsize=(3, 3), dpi=100)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter([0.50, 0.502, 0.504], [0.50, 0.50, 0.50], s=900)

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "marker_marker_overlaps")

        self.assertFalse(check["passed"])
        self.assertTrue(check["data"]["overlaps"])
        self.assertGreater(check["data"]["overlap_fraction"], 0.0)

    def test_marker_marker_overlaps_skip_when_marker_count_exceeds_cap(self):
        fig, ax = plt.subplots(figsize=(4, 4))
        xs = np.linspace(0.0, 1.0, MAX_TEXT_ARTISTS + 1)
        ys = np.zeros(MAX_TEXT_ARTISTS + 1)
        ax.scatter(xs, ys, s=40)

        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        check = _check(result, "marker_marker_overlaps")

        # Over-cap skip is informational, NOT a pass, and must not be counted as a pass.
        self.assertIsNone(check["passed"])
        self.assertTrue(check["detail"].startswith("skipped: marker count"))
        self.assertIsInstance(result["passed"], bool)

    def test_axis_label_title_overlap_reports_collision(self):
        fig, ax = plt.subplots(figsize=(2.0, 1.6))
        ax.set_ylabel("very long ylabel")
        ax.set_title("very long title")
        ax.yaxis.set_label_coords(0.5, 1.03)

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "axis_label_title_overlap")

        self.assertFalse(check["passed"])
        self.assertGreaterEqual(check["data"]["overlap_count"], 1)

    def test_axis_label_title_overlap_passes_for_normal_layout(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_ylabel("y")
        ax.set_title("title")

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "axis_label_title_overlap")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["overlap_count"], 0)

    def test_legend_marker_consistency_reports_open_marker_against_filled_key(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        label = "electret/leaky ctrl."
        ax.plot(
            [0.5],
            [0.5],
            marker="s",
            linestyle="none",
            markerfacecolor="none",
            markeredgecolor="gray",
            markersize=8,
            label=label,
        )
        legend_handle = Line2D(
            [],
            [],
            marker="s",
            linestyle="none",
            markerfacecolor="gray",
            markeredgecolor="gray",
            markersize=8,
            label=label,
        )
        ax.legend(handles=[legend_handle])
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_marker_consistency")

        self.assertFalse(check["passed"])
        mismatch = check["data"]["mismatches"][0]
        self.assertEqual(mismatch["legend_label"], label)
        self.assertEqual(mismatch["diff"], ["facecolor", "fill"])
        self.assertFalse(mismatch["data_style"]["fill"])
        self.assertTrue(mismatch["legend_style"]["fill"])

    def test_legend_marker_consistency_accepts_proxy_line_for_matching_scatter_shape(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        label = "electret/leaky ctrl."
        marker_diameter = 8.0
        scatter_area = np.pi * (marker_diameter / 2.0) ** 2
        ax.scatter([0.5], [0.5], marker="s", facecolors="gray", edgecolors="gray", s=scatter_area, label=label)
        legend_handle = Line2D(
            [],
            [],
            marker="s",
            linestyle="none",
            markerfacecolor="gray",
            markeredgecolor="gray",
            markersize=marker_diameter,
            label=label,
        )
        ax.legend(handles=[legend_handle])
        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_marker_consistency")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["mismatches"], [])

    def test_legend_marker_consistency_compares_scatter_area_as_visual_diameter(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        label = "area-matched marker"
        marker_diameter = 8.0
        scatter_area = np.pi * (marker_diameter / 2.0) ** 2
        ax.scatter([0.5], [0.5], marker="o", facecolors="gray", edgecolors="gray", s=scatter_area, label=label)
        legend_handle = Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markerfacecolor="gray",
            markeredgecolor="gray",
            markersize=marker_diameter,
            label=label,
        )
        ax.legend(handles=[legend_handle])

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_marker_consistency")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["mismatches"], [])

    def test_legend_marker_consistency_reports_variable_scatter_style_against_single_key(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        label = "composition"
        ax.scatter(
            [0.4, 0.6],
            [0.5, 0.5],
            marker="o",
            c=["red", "blue"],
            edgecolors=["black", "black"],
            s=[64, 64],
            label=label,
        )
        legend_handle = Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markerfacecolor="red",
            markeredgecolor="black",
            markersize=8,
            label=label,
        )
        ax.legend(handles=[legend_handle])

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_marker_consistency")

        self.assertFalse(check["passed"])
        mismatch = check["data"]["mismatches"][0]
        self.assertEqual(mismatch["legend_label"], label)
        self.assertIn("facecolor", mismatch["diff"])
        self.assertTrue(mismatch["data_style"]["variable_style"])

    def test_legend_marker_consistency_reports_markerless_line_style_drift(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        label = "series A"
        ax.plot([0.0, 1.0], [0.0, 1.0], color="red", linestyle="-", linewidth=2.0, label=label)
        legend_handle = Line2D([], [], color="blue", linestyle="--", linewidth=0.5, label=label)
        ax.legend(handles=[legend_handle])

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "legend_marker_consistency")

        self.assertFalse(check["passed"])
        mismatch = check["data"]["mismatches"][0]
        self.assertEqual(mismatch["legend_label"], label)
        self.assertEqual(set(mismatch["diff"]), {"line_color", "linestyle", "linewidth"})

    def test_label_offset_consistency_warns_for_repeated_label_direction_change(self):
        fig, axes = plt.subplots(1, 3, figsize=(6, 2))
        for ax in axes:
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.scatter([0.5], [0.5], s=80)
        axes[0].text(0.62, 0.5, "PDMS", ha="left", va="center")
        axes[1].text(0.62, 0.5, "PDMS", ha="left", va="center")
        axes[2].text(0.5, 0.38, "PDMS", ha="center", va="top")
        check = _check(
            diagnose_figure_geometry(_drawn(fig), list(axes), layout_locked=False), "label_offset_consistency"
        )

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

    def test_font_size_token_drift_reports_tick_label_sizes(self):
        fig, ax = plt.subplots()
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["A", "B", "C"], fontsize=30)

        check = _check(
            diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False, font_token_sizes=[6, 7, 8]),
            "font_size_token_drift",
        )

        self.assertFalse(check["passed"])
        self.assertTrue(any(item["role"] == "tick" and item["fontsize"] == 30.0 for item in check["data"]["offenders"]))

    def test_font_size_token_drift_reports_role_divergence_across_axes(self):
        fig, axes = plt.subplots(1, 2, figsize=(5, 2))
        axes[0].set_xlabel("left")
        axes[1].set_xlabel("right")
        axes[0].xaxis.label.set_fontsize(7.0)
        axes[1].xaxis.label.set_fontsize(8.0)

        check = _check(
            diagnose_figure_geometry(_drawn(fig), list(axes), layout_locked=False, font_token_sizes=[7.0, 8.0]),
            "font_size_token_drift",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["data"]["role_size_counts"]["axis"], 2)

    def test_journal_compliance_passes_normal_publication_geometry(self):
        fig, ax = plt.subplots(figsize=(57 / 25.4, 45.6 / 25.4))
        ax.plot([0, 1, 2], [0, 1, 0], linewidth=0.9, label="A")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        compliance = {
            "policy_id": "journal-nature/baseline",
            "target_format": "science",
            "min_font_size_pt": 5.0,
            "min_line_width_pt": 0.5,
            "max_figure_height_mm": 234.0,
        }

        check = _check(
            diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False, journal_compliance=compliance),
            "journal_compliance",
        )

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["target_format"], "science")
        self.assertEqual(check["data"]["font_offenders"], [])
        self.assertEqual(check["data"]["line_offenders"], [])
        self.assertFalse(check["data"]["height_offender"])

    def test_journal_compliance_reports_subfloor_and_overheight_output(self):
        fig, ax = plt.subplots(figsize=(57 / 25.4, 250 / 25.4))
        ax.plot([0, 1, 2], [0, 1, 0], linewidth=0.25, label="A")
        ax.set_xlabel("x")
        ax.xaxis.label.set_fontsize(4.0)
        ax.legend(fontsize=4.0)
        compliance = {
            "policy_id": "journal-nature/baseline",
            "target_format": "science",
            "min_font_size_pt": 5.0,
            "min_line_width_pt": 0.5,
            "max_figure_height_mm": 234.0,
        }

        check = _check(
            diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False, journal_compliance=compliance),
            "journal_compliance",
        )

        self.assertFalse(check["passed"])
        self.assertTrue(any(item["role"] == "axis" for item in check["data"]["font_offenders"]))
        self.assertTrue(any(item["linewidth"] == 0.25 for item in check["data"]["line_offenders"]))
        self.assertTrue(check["data"]["height_offender"])

    def test_all_skipped_warning_eligible_checks_report_unknown_overall_status(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        for index in range(MAX_TEXT_ARTISTS + 1):
            ax.annotate(str(index), (index / 500, index / 500))

        with patch("hub_core.geometry_diagnostics._WARNING_ELIGIBLE", frozenset({"point_annotation_overlaps"})):
            result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)

        self.assertIsNone(result["passed"])
        skipped = [
            check for check in result["checks"] if check["name"] in {"point_annotation_overlaps", "artist_overlaps"}
        ]
        self.assertTrue(any(check["passed"] is None for check in skipped))

    def test_artists_outside_axes_reports_informational_fraction_with_explicit_limits(self):
        fig, ax = plt.subplots()
        ax.plot([0, 100], [0, 100])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "artists_outside_axes")

        self.assertIsNone(check["passed"])
        self.assertIn("explicit limits", check["detail"])
        self.assertGreater(check["data"]["outside_fraction"], 0.0)

    def test_annotation_cap(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        for index in range(MAX_TEXT_ARTISTS + 1):
            ax.annotate(str(index), (index / 500, index / 500))
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        check = _check(result, "point_annotation_overlaps")
        self.assertIsNone(check["passed"])
        self.assertTrue(check["detail"].startswith("skipped: annotation count"))
        self.assertIsInstance(result["passed"], bool)

    def test_annotation_overlay_contrast_flags_dark_overlay_text(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        overlay = ax.axhspan(0.2, 0.8, color="black", alpha=0.9)
        overlay._graph_hub_overlay_role = "annotation_hspan"
        overlay._graph_hub_overlay_label = "dark band"
        text = ax.text(0.5, 0.5, "low contrast", color="black", ha="center", va="center")
        text._graph_hub_annotation_text_role = "annotation_hspan"

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "annotation_overlay_contrast")

        self.assertFalse(check["passed"])
        self.assertEqual(check["data"]["pairs"][0]["overlay_label"], "dark band")
        self.assertLess(check["data"]["pairs"][0]["contrast_ratio"], 3.0)
        plt.close(fig)

    def test_annotation_overlay_contrast_passes_light_text_on_dark_overlay(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        overlay = ax.axhspan(0.2, 0.8, color="black", alpha=0.9)
        overlay._graph_hub_overlay_role = "annotation_hspan"
        overlay._graph_hub_overlay_label = "dark band"
        text = ax.text(0.5, 0.5, "readable", color="white", ha="center", va="center")
        text._graph_hub_annotation_text_role = "annotation_hspan"

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "annotation_overlay_contrast")

        self.assertTrue(check["passed"])
        plt.close(fig)

    def test_annotation_overlay_contrast_ignores_untagged_point_label_text(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        overlay = ax.axhspan(0.2, 0.8, color="black", alpha=0.9)
        overlay._graph_hub_overlay_role = "annotation_hspan"
        overlay._graph_hub_overlay_label = "dark band"
        ax.text(0.5, 0.5, "point label", color="black", ha="center", va="center")

        check = _check(diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False), "annotation_overlay_contrast")

        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["pairs"], [])
        plt.close(fig)

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
            self.assertEqual(skipped["warnings"], ["skipped: render budget"])
            self.assertEqual(skipped["measurements"], [])

            # (b) generous deadline -> measurement runs
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 3600)
            measured = _safe_geometry_diagnostics_inline(fig)
            self.assertTrue(measured["measurements"])

            # (c) MCP_RENDER_TIMEOUT_SECONDS absent does not change either decision
            self.assertNotIn("MCP_RENDER_TIMEOUT_SECONDS", os.environ)
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 2.0)
            self.assertEqual(_safe_geometry_diagnostics_inline(fig)["measurements"], [])
            os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 3600)
            self.assertTrue(_safe_geometry_diagnostics_inline(fig)["measurements"])
        finally:
            if prior is None:
                os.environ.pop("GEOMETRY_DIAGNOSTICS_DEADLINE", None)
            else:
                os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = prior
            if prior_timeout is not None:
                os.environ["MCP_RENDER_TIMEOUT_SECONDS"] = prior_timeout

    def test_scatter_marker_footprint_diameter_uses_area_formula(self):
        # matplotlib scatter `s` is area in pt^2; diameter = 2*sqrt(s/pi), not sqrt(s).
        fig, ax = plt.subplots(figsize=(3, 3), dpi=100)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        size = 400.0  # sqrt -> 20pt (wrong); 2*sqrt(s/pi) -> ~22.57pt (correct)
        ax.scatter([0.5], [0.5], s=size)
        _drawn(fig)
        ((_label, box),) = _marker_footprint_box_entries(ax, fig)
        px_per_point = fig.dpi / 72.0
        expected_diameter_px = 2.0 * float(np.sqrt(size / np.pi)) * px_per_point
        self.assertAlmostEqual(box.width, expected_diameter_px, places=4)
        self.assertAlmostEqual(box.height, expected_diameter_px, places=4)

    def test_data_only_marker_over_cap_does_not_skip_artist_overlaps(self):
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        xs = np.linspace(0.0, 1.0, MAX_TEXT_ARTISTS + 1)
        ys = np.zeros(MAX_TEXT_ARTISTS + 1)
        ax.scatter(xs, ys, s=40)
        result = diagnose_figure_geometry(_drawn(fig), [ax], layout_locked=False)
        check = _check(result, "artist_overlaps")
        self.assertTrue(check["passed"])
        self.assertEqual(check["data"]["overlaps"], [])
        self.assertEqual(check["data"]["candidate_pairs"], 0)
        self.assertIsInstance(result["passed"], bool)

    def test_box_vector_away_tie_break_is_deterministic(self):
        # Coincident centers force the seeded tie-break branch.
        source = Bbox.from_extents(0.0, 0.0, 2.0, 2.0)
        obstacle = Bbox.from_extents(0.0, 0.0, 2.0, 2.0)
        # In-process hash() is stable, so this set-size check only confirms intra-run
        # consistency, not cross-run reproducibility. Per-run reproducibility (stable
        # across PYTHONHASHSEED values) is proven by the value equality assertion below,
        # which pins the result to a hashlib-derived (seed-independent) angle.
        vectors = {_box_vector_away(source, obstacle, step_px=5.0) for _ in range(8)}
        self.assertEqual(len(vectors), 1)
        angle_seed = (round(1.0, 3), round(1.0, 3), round(1.0, 3), round(1.0, 3), round(5.0, 3))
        angle = (int(hashlib.sha256(repr(angle_seed).encode()).hexdigest(), 16) % 360) * np.pi / 180.0
        expected = (float(np.cos(angle) * 5.0), float(np.sin(angle) * 5.0))
        self.assertEqual(vectors.pop(), expected)
        # Witness that the formula uses hashlib, not Python's PYTHONHASHSEED-dependent hash().
        hash_angle = (hash(angle_seed) % 360) * np.pi / 180.0
        hash_vector = (float(np.cos(hash_angle) * 5.0), float(np.sin(hash_angle) * 5.0))
        self.assertNotEqual(expected, hash_vector)

    def test_box_vector_away_escapes_wide_thin_line_on_short_axis(self):
        source = Bbox.from_extents(340.0, 284.0, 466.0, 312.0)
        obstacle = Bbox.from_extents(119.0, 295.0, 495.0, 299.0)

        dx, dy = _box_vector_away(source, obstacle, step_px=4.0)

        self.assertEqual(dx, 0.0)
        self.assertGreater(abs(dy), 4.0)


if __name__ == "__main__":
    unittest.main()
