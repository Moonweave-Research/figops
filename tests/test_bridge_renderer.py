import hashlib
import os
import tempfile
import unittest
import warnings
from csv import DictWriter
from pathlib import Path
from unittest.mock import MagicMock, patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

from hub_core.geometry_diagnostics import _marker_footprint_box_entries, diagnose_figure_geometry
from plotting.bridge_renderer import (
    BridgeFigureSpec,
    MultiPanelSpec,
    _annotate_points,
    _annotation_font_size,
    _apply_axes_metadata,
    _apply_layout,
    _avoid_smart_legend_data_collision,
    _display_label,
    _draw_annotations,
    _draw_manual_overlays,
    _figsize_for_format,
    _render_bar_plot,
    _render_heatmap_plot,
    _render_multipanel_draft,
    _render_plot,
    _render_xy_plot,
    _resolved_legend_layout,
    render_bridge_figure,
)
from themes.journal_theme import apply_journal_theme, save_journal_fig


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _geometry_check(result: dict, name: str) -> dict:
    matches = [check for check in result["checks"] if check["name"] == name]
    assert matches, f"no geometry check named {name}"
    return matches[0]


def _assert_marker_footprints_inside_axes(testcase: unittest.TestCase, fig, axes) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        axes_box = ax.get_window_extent(renderer)
        marker_boxes = _marker_footprint_box_entries(ax, fig)
        testcase.assertTrue(marker_boxes)
        for label, marker_box in marker_boxes:
            testcase.assertGreaterEqual(marker_box.x0, axes_box.x0, label)
            testcase.assertLessEqual(marker_box.x1, axes_box.x1, label)
            testcase.assertGreaterEqual(marker_box.y0, axes_box.y0, label)
            testcase.assertLessEqual(marker_box.y1, axes_box.y1, label)


def _subplot_grid_shape(axes) -> tuple[int, int]:
    visible = [ax for ax in axes if ax.get_visible()]
    assert visible, "no visible axes"
    n_rows, n_cols, *_ = visible[0].get_subplotspec().get_geometry()
    for ax in visible:
        rows, cols, *_ = ax.get_subplotspec().get_geometry()
        assert (rows, cols) == (n_rows, n_cols)
    return int(n_rows), int(n_cols)


def _legend_diagnostic(result: dict) -> dict:
    return _geometry_check(result, "legend_data_collision")


def _legend_is_inside_axes(fig, ax) -> bool:
    fig.canvas.draw()
    legend = ax.get_legend()
    if legend is None:
        return False
    renderer = fig.canvas.get_renderer()
    legend_box = legend.get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    return (
        legend_box.x0 >= axes_box.x0
        and legend_box.x1 <= axes_box.x1
        and legend_box.y0 >= axes_box.y0
        and legend_box.y1 <= axes_box.y1
    )


class BridgeRendererUnitTest(unittest.TestCase):
    def _write_xy_csv(self, root: Path, name: str) -> Path:
        csv_path = root / name
        csv_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
        return csv_path

    def _write_distribution_csv(self, root: Path, name: str, *, n_per_group: int = 12) -> Path:
        csv_path = root / name
        rows = []
        for group_idx, group in enumerate(("control", "treated")):
            for idx in range(n_per_group):
                rows.append({"condition": group, "modulus": 1.0 + group_idx + idx * 0.03})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = DictWriter(handle, fieldnames=["condition", "modulus"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def _write_facet_csv(self, root: Path, name: str) -> Path:
        csv_path = root / name
        rows = []
        for facet_idx, facet in enumerate(("low strain", "high strain", "recovered")):
            for idx in range(4):
                rows.append({"cycle": idx, "stress": facet_idx + idx * 0.25, "phase": facet})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = DictWriter(handle, fieldnames=["cycle", "stress", "phase"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def _facet_points(self, n_facets: int, *, n_points: int = 3) -> list[dict]:
        points = []
        for facet_idx in range(n_facets):
            for idx in range(n_points):
                points.append(
                    {
                        "x": float(idx),
                        "y": float(facet_idx) + idx * 0.2,
                        "label": "",
                        "series": "",
                        "yerr": None,
                        "yerr_minus": None,
                        "facet": f"facet {facet_idx}",
                    }
                )
        return points

    def _render_facet_grid(self, points: list[dict], spec: BridgeFigureSpec):
        fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
        try:
            _render_plot(ax, points, spec)
            _apply_layout(fig, ax, spec)
            axes = [facet_ax for facet_ax in fig.axes if facet_ax.get_visible()]
            return fig, axes
        except Exception:
            plt.close(fig)
            raise

    def _cross_track_collision_points(self) -> list[dict]:
        series_defs = {
            "Control": (1.00, 0.18),
            "Treatment A": (1.18, 0.24),
            "Treatment B": (0.88, 0.31),
        }
        points = []
        for idx, x_value in enumerate([0, 1, 2, 3, 4, 5]):
            for series_name, (base, slope) in series_defs.items():
                curvature = 0.025 * (idx - 2) ** 2 if series_name == "Treatment A" else 0.015 * idx
                if series_name == "Treatment B":
                    curvature = -0.018 * (idx - 1) ** 2 + 0.09
                points.append(
                    {
                        "x": float(x_value),
                        "y": float(base + slope * x_value + curvature),
                        "label": "",
                        "series": series_name,
                        "yerr": float(0.055 + 0.012 * idx + (0.015 if series_name == "Treatment A" else 0.0)),
                        "yerr_minus": None,
                        "facet": "",
                    }
                )
        return points

    def _render_bridge_like_axes(self, points: list[dict], target_format: str, *, title: str = "Legend placement"):
        saved_rc = plt.rcParams.copy()
        apply_journal_theme(target_format)
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="time_h",
            y_column="response",
            title=title,
            x_axis_label="Time (h)",
            y_axis_label="Normalized response",
            series_column="series",
            yerr_column="err" if any(point.get("yerr") is not None for point in points) else "",
            target_format=target_format,
        )
        fig, ax = plt.subplots(figsize=_figsize_for_format(target_format))
        try:
            _render_plot(ax, points, spec)
            _apply_axes_metadata(ax, spec)
            ax.set_title(spec.title)
            _apply_layout(fig, ax, spec)
            return fig, ax, saved_rc
        except Exception:
            plt.rcParams.update(saved_rc)
            plt.close(fig)
            raise

    def _close_bridge_like_axes(self, fig, saved_rc) -> None:
        plt.rcParams.update(saved_rc)
        plt.close(fig)

    def _write_overlay_csv(self, root: Path, name: str) -> Path:
        csv_path = root / name
        rows = [
            {"strain": 0.0, "stress": 0.9},
            {"strain": 1.0, "stress": 1.9},
            {"strain": 2.0, "stress": 3.2},
            {"strain": 3.0, "stress": 4.1},
            {"strain": 4.0, "stress": 5.2},
            {"strain": 5.0, "stress": 6.1},
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = DictWriter(handle, fieldnames=["strain", "stress"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def _write_replicate_bar_csv(self, root: Path, name: str) -> Path:
        csv_path = root / name
        rows = [
            {"condition": "control", "value": 1.0},
            {"condition": "control", "value": 3.0},
            {"condition": "treated", "value": 2.0},
            {"condition": "treated", "value": 4.0},
            {"condition": "treated", "value": 6.0},
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = DictWriter(handle, fieldnames=["condition", "value"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def _write_bar_error_csv(self, root: Path, name: str) -> Path:
        csv_path = root / name
        rows = [
            {"condition": "control", "value": 1.2, "sem": 0.1},
            {"condition": "treated", "value": 2.4, "sem": 0.2},
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = DictWriter(handle, fieldnames=["condition", "value", "sem"])
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def test_display_label_uses_shared_compression_rules(self):
        raw = "Coated Sample_Noa_None_Aligned"
        compressed = _display_label(raw)
        self.assertEqual(compressed, "Coated, Noa, None, Aln.")

    def test_display_label_can_preserve_raw_text(self):
        raw = "Coated Sample_Noa_None_Aligned"
        preserved = _display_label(raw, compress_labels=False)
        self.assertEqual(preserved, raw)

    def test_bar_plot_applies_compressed_tick_labels(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="bar",
            x_column="condition",
            y_column="value",
            title="bar",
        )
        points = [
            {"x": "Coated Sample_A_Aligned", "y": 1.0, "label": "", "series": "", "yerr": None},
            {"x": "Coated Sample_B_Unaligned", "y": 2.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_bar_plot(ax, points, spec)
            labels = [item.get_text() for item in ax.get_xticklabels()]
            self.assertIn("Coated, A, Aln.", labels)
            self.assertIn("Coated, B, Unaln.", labels)
        finally:
            plt.close(fig)

    def test_render_bridge_figure_draws_guide_curve_and_fill_between_region(self):
        with tempfile.TemporaryDirectory(prefix="bridge_overlay_primitives_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "overlay.csv"
            csv_path.write_text(
                "x,y,lower,upper\n0,1,0.5,1.5\n1,2,1.5,2.5\n2,3,2.5,3.5\n",
                encoding="utf-8",
            )
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "overlay.png"),
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="overlay primitives",
                guide_curves=(
                    {
                        "points": [{"x": 0, "y": 1.1}, {"x": 1, "y": 2.2}, {"x": 2, "y": 3.1}],
                        "label": "guide",
                        "color": "red",
                    },
                ),
                fill_between=(
                    {
                        "y1_column": "lower",
                        "y2_column": "upper",
                        "label": "band",
                        "color": "blue",
                        "alpha": 0.2,
                    },
                ),
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["line_labels"] = [line.get_label() for line in ax.lines]
                observed["band_labels"] = [
                    collection.get_label()
                    for collection in ax.collections
                    if isinstance(collection, PolyCollection)
                ]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertIn("guide", observed["line_labels"])
            self.assertIn("band", observed["band_labels"])

    def test_bar_plot_aggregate_mean_collapses_duplicate_categories(self):
        with tempfile.TemporaryDirectory(prefix="bridge_bar_aggregate_mean_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_replicate_bar_csv(tmpdir_path, "bar.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "bar.png"),
                plot_type="bar",
                x_column="condition",
                y_column="value",
                title="bar",
                aggregate="mean",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["heights"] = [bar.get_height() for bar in ax.patches]
                observed["tick_labels"] = [label.get_text() for label in ax.get_xticklabels()]
                Path(output_path).write_bytes(b"png")

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                    out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["tick_labels"], ["control", "treated"])
            self.assertEqual(observed["heights"], [2.0, 4.0])
            self.assertFalse(any("duplicate category" in str(item.message) for item in caught))

    def test_bar_plot_aggregate_median_collapses_duplicate_categories(self):
        with tempfile.TemporaryDirectory(prefix="bridge_bar_aggregate_median_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "bar.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = DictWriter(handle, fieldnames=["condition", "value"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"condition": "control", "value": 1.0},
                        {"condition": "control", "value": 3.0},
                        {"condition": "control", "value": 100.0},
                        {"condition": "treated", "value": 2.0},
                        {"condition": "treated", "value": 4.0},
                        {"condition": "treated", "value": 200.0},
                    ]
                )
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "bar.png"),
                plot_type="bar",
                x_column="condition",
                y_column="value",
                title="bar",
                aggregate="median",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["heights"] = [bar.get_height() for bar in ax.patches]
                observed["tick_labels"] = [label.get_text() for label in ax.get_xticklabels()]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["tick_labels"], ["control", "treated"])
            self.assertEqual(observed["heights"], [3.0, 4.0])

    def test_bar_plot_rejects_invalid_aggregate(self):
        with tempfile.TemporaryDirectory(prefix="bridge_bar_aggregate_invalid_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_replicate_bar_csv(tmpdir_path, "bar.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "bar.png"),
                plot_type="bar",
                x_column="condition",
                y_column="value",
                title="bar",
                aggregate="mode",
            )

            with self.assertRaises(ValueError) as ctx:
                render_bridge_figure(spec)

            self.assertIn("aggregate", str(ctx.exception))
            self.assertIn("mean", str(ctx.exception))

    def test_bar_plot_aggregate_matches_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_2_grouped_bar_aggregate.png"
        with tempfile.TemporaryDirectory(prefix="bridge_bar_aggregate_baseline_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_replicate_bar_csv(tmpdir_path, "bar.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "bar.png"),
                plot_type="bar",
                x_column="condition",
                y_column="value",
                title="Grouped-bar aggregate",
                aggregate="mean",
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            from PIL import Image

            with Image.open(out) as image:
                dpi = image.info.get("dpi")
            self.assertIsNotNone(dpi)
            self.assertAlmostEqual(dpi[0], 600, delta=1)
            self.assertAlmostEqual(dpi[1], 600, delta=1)
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))

    def test_heatmap_plot_renders_mesh_and_colorbar(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="heatmap",
            x_column="x",
            y_column="y",
            z_column="z",
            title="heatmap",
        )
        points = [
            {"x": 0.0, "y": 0.0, "z": 1.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 0.0, "z": 2.0, "label": "", "series": "", "yerr": None},
            {"x": 0.0, "y": 1.0, "z": 3.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 1.0, "z": 4.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_heatmap_plot(ax, points, spec)
            self.assertEqual(len(ax.collections), 1)
            mesh = ax.collections[0]
            self.assertEqual(mesh.get_array().count(), 4)
            self.assertEqual(len(fig.axes), 2)
            self.assertEqual(fig.axes[1].get_ylabel(), "z")
        finally:
            plt.close(fig)

    def test_heatmap_plot_does_not_annotate_cell_values_by_default(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="heatmap",
            x_column="x",
            y_column="y",
            z_column="z",
            title="heatmap",
        )
        points = [
            {"x": 0.0, "y": 0.0, "z": 1.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 0.0, "z": 2.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_heatmap_plot(ax, points, spec)
            self.assertEqual([text.get_text() for text in ax.texts], [])
        finally:
            plt.close(fig)

    def test_heatmap_plot_annotates_cell_values_with_contrast(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="heatmap",
            x_column="x",
            y_column="y",
            z_column="z",
            title="heatmap",
            annotate_values=True,
        )
        points = [
            {"x": 0.0, "y": 0.0, "z": 0.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 0.0, "z": 1000.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_heatmap_plot(ax, points, spec)
            labels = [text.get_text() for text in ax.texts]
            colors = [text.get_color() for text in ax.texts]
            self.assertEqual(labels, ["0", "1e+03"])
            self.assertEqual(colors, ["white", "black"])
        finally:
            plt.close(fig)

    def test_single_series_bar_renders_declared_error_column(self):
        with tempfile.TemporaryDirectory(prefix="bridge_bar_yerr_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_bar_error_csv(tmpdir_path, "bar.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "bar.png"),
                plot_type="bar",
                x_column="condition",
                y_column="value",
                yerr_column="sem",
                title="bar",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["line_count"] = len(ax.lines)
                observed["bar_count"] = len(ax.patches)
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                render_bridge_figure(spec)

            self.assertEqual(observed["bar_count"], 2)
            self.assertGreater(observed["line_count"], 0)

    def test_box_plot_type_renders_csv_distribution_with_points(self):
        with tempfile.TemporaryDirectory(prefix="bridge_box_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_distribution_csv(tmpdir_path, "box.csv", n_per_group=4)
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "box.png"),
                plot_type="box",
                x_column="condition",
                y_column="modulus",
                title="box",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["xtick_labels"] = [item.get_text() for item in ax.get_xticklabels()]
                observed["collections"] = len(ax.collections)
                observed["lines"] = len(ax.lines)
                Path(output_path).write_bytes(b"png")

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                    out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["xtick_labels"], ["control", "treated"])
            self.assertGreaterEqual(observed["collections"], 2)
            self.assertGreaterEqual(observed["lines"], 2)
            self.assertTrue(any("Individual data points" in str(item.message) for item in caught))

    def test_violin_plot_type_renders_csv_distribution_with_violin_bodies(self):
        with tempfile.TemporaryDirectory(prefix="bridge_violin_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_distribution_csv(tmpdir_path, "violin.csv", n_per_group=12)
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "violin.png"),
                plot_type="violin",
                x_column="condition",
                y_column="modulus",
                title="violin",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["xtick_labels"] = [item.get_text() for item in ax.get_xticklabels()]
                observed["violin_bodies"] = [
                    collection for collection in ax.collections if "PolyCollection" in type(collection).__name__
                ]
                observed["point_collections"] = [
                    collection
                    for collection in ax.collections
                    if "PathCollection" in type(collection).__name__
                    and hasattr(collection, "get_offsets")
                    and len(collection.get_offsets()) > 0
                ]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["xtick_labels"], ["control", "treated"])
            self.assertGreaterEqual(len(observed["violin_bodies"]), 2)
            self.assertTrue(
                all(len(path.vertices) >= 500 for body in observed["violin_bodies"] for path in body.get_paths())
            )
            self.assertEqual(sum(len(collection.get_offsets()) for collection in observed["point_collections"]), 24)

    def test_box_plot_type_matches_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_2_box_plot.png"
        with tempfile.TemporaryDirectory(prefix="bridge_box_baseline_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_distribution_csv(tmpdir_path, "box.csv", n_per_group=12)
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "box.png"),
                plot_type="box",
                x_column="condition",
                y_column="modulus",
                title="Box distribution",
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))

    def test_violin_plot_type_matches_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_2_violin_plot.png"
        with tempfile.TemporaryDirectory(prefix="bridge_violin_baseline_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_distribution_csv(tmpdir_path, "violin.csv", n_per_group=12)
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "violin.png"),
                plot_type="violin",
                x_column="condition",
                y_column="modulus",
                title="Violin distribution",
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))

    def test_axis_scales_series_and_annotations_render_on_bridge_figure(self):
        with tempfile.TemporaryDirectory(prefix="bridge_log_series_annotation_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "series.csv"
            csv_path.write_text(
                "x,y,condition\n1,10,A\n2,100,A\n1,20,B\n2,200,B\n",
                encoding="utf-8",
            )
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "series.png"),
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="Series",
                series_column="condition",
                y_scale="log",
                annotations=({"x": 2.0, "y": 200.0, "text": "~10x", "arrow_to": {"x": 1.0, "y": 20.0}},),
            )
            observed = {}

            def capture_figure(fig, output_path, **_kwargs):
                ax = fig.axes[0]
                observed["yscale"] = ax.get_yscale()
                observed["legend"] = [text.get_text() for text in ax.get_legend().get_texts()]
                observed["texts"] = [text.get_text() for text in ax.texts]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                render_bridge_figure(spec)

            self.assertEqual(observed["yscale"], "log")
            self.assertEqual(observed["legend"], ["A", "B"])
            self.assertIn("~10x", observed["texts"])

    def test_save_journal_png_embeds_dpi_metadata(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(prefix="bridge_png_dpi_") as tmpdir:
            out = Path(tmpdir) / "figure.png"
            fig, ax = plt.subplots()
            try:
                ax.plot([0, 1], [1, 2])
                save_journal_fig(fig, out)
            finally:
                plt.close(fig)

            with Image.open(out) as image:
                dpi = image.info.get("dpi")
            self.assertIsNotNone(dpi)
            self.assertAlmostEqual(dpi[0], 600, delta=1)
            self.assertAlmostEqual(dpi[1], 600, delta=1)

    def test_facet_suptitle_reserves_headroom_and_diagnostics_check_it(self):
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 0.0, "y": 3.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
            {"x": 1.0, "y": 4.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
        ]
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="x",
            y_column="y",
            title="Long facet title that must not collide with panel headers",
            facet_column="phase",
            facet_ncols=2,
        )

        fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
        try:
            _render_plot(ax, points, spec)
            _apply_layout(fig, ax, spec)
            axes = [facet_ax for facet_ax in fig.axes if facet_ax.get_visible()]
            result = diagnose_figure_geometry(fig, axes, layout_locked=False)
            check = _geometry_check(result, "figure_title_panel_title_overlap")
            self.assertTrue(check["passed"], check)
        finally:
            plt.close(fig)

    def test_facet_annotations_render_once_not_once_per_panel(self):
        with tempfile.TemporaryDirectory(prefix="bridge_facet_annotation_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_facet_csv(tmpdir_path, "facet.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "facet.png"),
                plot_type="facet",
                x_column="cycle",
                y_column="stress",
                title="Facet annotation",
                facet_column="phase",
                annotations=({"x": 1.0, "y": 1.0, "text": "callout"},),
            )
            observed = {}

            def capture_figure(fig, output_path, **_kwargs):
                observed["annotation_count"] = sum(
                    1 for axis in fig.axes for text in axis.texts if text.get_text() == "callout"
                )
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                render_bridge_figure(spec)

            self.assertEqual(observed["annotation_count"], 1)

    def test_facet_plot_type_renders_one_subplot_per_facet(self):
        with tempfile.TemporaryDirectory(prefix="bridge_facet_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_facet_csv(tmpdir_path, "facet.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "facet.png"),
                plot_type="facet",
                x_column="cycle",
                y_column="stress",
                title="Facet stress",
                facet_column="phase",
            )
            observed = {}

            def capture_figure(fig, output_path):
                axes = [ax for ax in fig.axes if ax.get_visible()]
                observed["titles"] = [ax.get_title() for ax in axes]
                observed["line_counts"] = [len(ax.lines) for ax in axes]
                observed["xlabels"] = [ax.get_xlabel() for ax in axes]
                observed["ylabels"] = [ax.get_ylabel() for ax in axes]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["titles"], ["low strain", "high strain", "recovered"])
            self.assertEqual(observed["line_counts"], [1, 1, 1])
            self.assertEqual(observed["xlabels"], ["", "", "cycle"])
            self.assertEqual(observed["ylabels"], ["stress", "", "stress"])

    def test_facet_plot_type_uses_shared_axis_limits_by_default(self):
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 10.0, "y": 100.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
            {"x": 20.0, "y": 120.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
            {"x": -5.0, "y": -20.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "C"},
            {"x": -4.0, "y": -10.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "C"},
        ]
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="cycle",
            y_column="stress",
            title="Facet stress",
            facet_column="phase",
            target_format="nature",
            profile_name="baseline",
        )

        fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
        try:
            _render_plot(ax, points, spec)
            _apply_layout(fig, ax, spec)
            axes = [facet_ax for facet_ax in fig.axes if facet_ax.get_visible()]
            self.assertEqual(len(axes), 3)
            x_limits = {tuple(round(value, 10) for value in facet_ax.get_xlim()) for facet_ax in axes}
            y_limits = {tuple(round(value, 10) for value in facet_ax.get_ylim()) for facet_ax in axes}
            self.assertEqual(len(x_limits), 1)
            self.assertEqual(len(y_limits), 1)
            _assert_marker_footprints_inside_axes(self, fig, axes)
        finally:
            plt.close(fig)

    def test_facet_plot_type_can_opt_into_free_axis_limits(self):
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "A"},
            {"x": 10.0, "y": 100.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
            {"x": 20.0, "y": 120.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": "B"},
        ]
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="cycle",
            y_column="stress",
            title="Facet stress",
            facet_column="phase",
            facet_scales="free",
            target_format="nature",
            profile_name="baseline",
        )

        fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
        try:
            _render_plot(ax, points, spec)
            axes = [facet_ax for facet_ax in fig.axes if facet_ax.get_visible()]
            self.assertEqual(len(axes), 2)
            x_limits = {tuple(round(value, 10) for value in facet_ax.get_xlim()) for facet_ax in axes}
            y_limits = {tuple(round(value, 10) for value in facet_ax.get_ylim()) for facet_ax in axes}
            self.assertEqual(len(x_limits), 2)
            self.assertEqual(len(y_limits), 2)
        finally:
            plt.close(fig)

    def test_nature_single_panel_line_and_scatter_markers_are_token_sized_and_not_clipped(self):
        points = [
            {"x": 0.0, "y": 0.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": ""},
            {"x": 1.0, "y": 1.0, "label": "", "series": "", "yerr": None, "yerr_minus": None, "facet": ""},
        ]

        for plot_type, line in (("line", True), ("scatter", False)):
            with self.subTest(plot_type=plot_type):
                spec = BridgeFigureSpec(
                    csv_path="unused.csv",
                    output_path="unused.png",
                    plot_type=plot_type,
                    x_column="x",
                    y_column="y",
                    title="Edge points",
                    target_format="nature",
                    profile_name="baseline",
                )
                fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
                try:
                    _render_xy_plot(ax, points, spec, line=line)
                    if line:
                        self.assertEqual({artist.get_markersize() for artist in ax.lines}, {3.2})
                    else:
                        scatter_sizes = {
                            round(float(size), 4) for collection in ax.collections for size in collection.get_sizes()
                        }
                        self.assertEqual(scatter_sizes, {8.0425})
                    _assert_marker_footprints_inside_axes(self, fig, [ax])
                finally:
                    plt.close(fig)

    def test_science_bridge_figsize_uses_aaas_single_column_width(self):
        science_w_in, science_h_in = _figsize_for_format("science")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(science_w_in * 25.4, 57.0, places=4)
        self.assertAlmostEqual(science_h_in * 25.4, 45.6, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_acs_bridge_figsize_uses_acs_single_column_width(self):
        acs_w_in, acs_h_in = _figsize_for_format("acs")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(acs_w_in * 25.4, 84.67, places=4)
        self.assertAlmostEqual(acs_h_in * 25.4, 67.736, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_wiley_bridge_figsize_uses_wiley_single_column_width(self):
        wiley_w_in, wiley_h_in = _figsize_for_format("wiley")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(wiley_w_in * 25.4, 85.0, places=4)
        self.assertAlmostEqual(wiley_h_in * 25.4, 68.0, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_cell_bridge_figsize_uses_cell_press_single_column_width(self):
        cell_w_in, cell_h_in = _figsize_for_format("cell")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(cell_w_in * 25.4, 85.0, places=4)
        self.assertAlmostEqual(cell_h_in * 25.4, 68.0, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_rsc_bridge_figsize_uses_rsc_single_column_width(self):
        rsc_w_in, rsc_h_in = _figsize_for_format("rsc")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(rsc_w_in * 25.4, 83.0, places=4)
        self.assertAlmostEqual(rsc_h_in * 25.4, 66.4, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_elsevier_bridge_figsize_uses_elsevier_single_column_width(self):
        elsevier_w_in, elsevier_h_in = _figsize_for_format("elsevier")
        nature_w_in, nature_h_in = _figsize_for_format("nature")

        self.assertAlmostEqual(elsevier_w_in * 25.4, 90.0, places=4)
        self.assertAlmostEqual(elsevier_h_in * 25.4, 72.0, places=4)
        self.assertAlmostEqual(nature_w_in * 25.4, 88.0, places=4)
        self.assertAlmostEqual(nature_h_in * 25.4, 71.0, places=4)

    def test_science_multipanel_draft_uses_aaas_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="science",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 121.0, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_cell_multipanel_draft_uses_cell_press_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="cell",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 174.0, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_rsc_multipanel_draft_uses_rsc_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="rsc",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 171.0, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_elsevier_multipanel_draft_uses_elsevier_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="elsevier",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 190.0, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_acs_multipanel_draft_uses_acs_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="acs",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 177.8, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_wiley_multipanel_draft_uses_wiley_column_width_tokens(self):
        spec = MultiPanelSpec(
            panels=(),
            output_path="unused.png",
            rows=1,
            cols=1,
            target_format="wiley",
            column_width="double",
            panel_height_mm=40.0,
        )

        fig = _render_multipanel_draft(spec)
        try:
            width_mm, height_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(width_mm, 178.0, places=4)
            self.assertAlmostEqual(height_mm, 40.0, places=4)
        finally:
            plt.close(fig)

    def test_nature_facet_markers_are_smaller_and_not_clipped_by_axes_edges(self):
        points = self._facet_points(9, n_points=2)
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="cycle",
            y_column="stress",
            title="Facet stress",
            facet_column="phase",
            target_format="nature",
            profile_name="baseline",
        )

        fig, axes = self._render_facet_grid(points, spec)
        try:
            self.assertEqual(len(axes), 9)
            line_marker_sizes = {line.get_markersize() for facet_ax in axes for line in facet_ax.lines}
            self.assertEqual(line_marker_sizes, {2.4})
            x_limits = {tuple(round(value, 10) for value in facet_ax.get_xlim()) for facet_ax in axes}
            y_limits = {tuple(round(value, 10) for value in facet_ax.get_ylim()) for facet_ax in axes}
            self.assertEqual(len(x_limits), 1)
            self.assertEqual(len(y_limits), 1)
            _assert_marker_footprints_inside_axes(self, fig, axes)
        finally:
            plt.close(fig)

    def test_facet_ncols_controls_subplot_grid_columns(self):
        points = self._facet_points(7)
        for requested_cols, expected_rows in ((2, 4), (4, 2)):
            with self.subTest(requested_cols=requested_cols):
                spec = BridgeFigureSpec(
                    csv_path="unused.csv",
                    output_path="unused.png",
                    plot_type="facet",
                    x_column="cycle",
                    y_column="stress",
                    title="Facet stress",
                    facet_column="phase",
                    target_format="nature",
                    profile_name="baseline",
                    facet_ncols=requested_cols,
                )

                fig, axes = self._render_facet_grid(points, spec)
                try:
                    self.assertEqual(_subplot_grid_shape(axes), (expected_rows, requested_cols))
                    _assert_marker_footprints_inside_axes(self, fig, axes)
                finally:
                    plt.close(fig)

    def test_facet_nrows_controls_subplot_grid_rows(self):
        points = self._facet_points(7)
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="cycle",
            y_column="stress",
            title="Facet stress",
            facet_column="phase",
            target_format="nature",
            profile_name="baseline",
            facet_nrows=2,
        )

        fig, axes = self._render_facet_grid(points, spec)
        try:
            self.assertEqual(_subplot_grid_shape(axes), (2, 4))
            _assert_marker_footprints_inside_axes(self, fig, axes)
        finally:
            plt.close(fig)

    def test_facet_layout_rejects_invalid_explicit_grid(self):
        points = self._facet_points(7)
        for overrides, message in (
            ({"facet_ncols": 0}, "facet_ncols must be a positive integer"),
            ({"facet_nrows": "2"}, "facet_nrows must be a positive integer"),
            ({"facet_ncols": 3, "facet_nrows": 2}, "must hold 7 facets"),
        ):
            with self.subTest(overrides=overrides):
                spec = BridgeFigureSpec(
                    csv_path="unused.csv",
                    output_path="unused.png",
                    plot_type="facet",
                    x_column="cycle",
                    y_column="stress",
                    title="Facet stress",
                    facet_column="phase",
                    target_format="nature",
                    profile_name="baseline",
                    **overrides,
                )
                fig, ax = plt.subplots(figsize=(89 / 25.4, 71 / 25.4), dpi=100)
                try:
                    with self.assertRaisesRegex(ValueError, message):
                        _render_plot(ax, points, spec)
                finally:
                    plt.close(fig)

    def test_facet_auto_layout_can_exceed_three_columns_for_large_facet_sets(self):
        points = self._facet_points(16)
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="facet",
            x_column="cycle",
            y_column="stress",
            title="Facet stress",
            facet_column="phase",
            target_format="nature",
            profile_name="baseline",
        )

        fig, axes = self._render_facet_grid(points, spec)
        try:
            self.assertEqual(_subplot_grid_shape(axes), (4, 4))
            _assert_marker_footprints_inside_axes(self, fig, axes)
        finally:
            plt.close(fig)

    def test_facet_plot_type_matches_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_2_facet_plot.png"
        with tempfile.TemporaryDirectory(prefix="bridge_facet_baseline_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_facet_csv(tmpdir_path, "facet.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "facet.png"),
                plot_type="facet",
                x_column="cycle",
                y_column="stress",
                title="Facet stress",
                facet_column="phase",
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))

    def test_statistical_overlays_render_fit_ci_and_significance_marker(self):
        with tempfile.TemporaryDirectory(prefix="bridge_stat_overlay_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_overlay_csv(tmpdir_path, "overlay.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "overlay.png"),
                plot_type="scatter",
                x_column="strain",
                y_column="stress",
                title="Stat overlays",
                fit_line=True,
                ci_band=True,
                significance_markers=({"x1": 1.0, "x2": 4.0, "y": 5.6, "label": "p<0.01"},),
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                observed["line_labels"] = [line.get_label() for line in ax.lines]
                observed["collections"] = [type(collection).__name__ for collection in ax.collections]
                observed["texts"] = [text.get_text() for text in ax.texts]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertIn("Linear fit", observed["line_labels"])
            self.assertTrue(any("PolyCollection" in name for name in observed["collections"]))
            self.assertIn("p<0.01", observed["texts"])

    def test_statistical_overlay_rejects_invalid_significance_marker(self):
        with tempfile.TemporaryDirectory(prefix="bridge_stat_overlay_invalid_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_overlay_csv(tmpdir_path, "overlay.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "overlay.png"),
                plot_type="scatter",
                x_column="strain",
                y_column="stress",
                title="Stat overlays",
                significance_markers=({"x1": 1.0, "y": 5.6, "label": "p<0.01"},),
            )

            with self.assertRaises(ValueError) as ctx:
                render_bridge_figure(spec)

            self.assertIn("significance_markers[0]", str(ctx.exception))
            self.assertIn("x2", str(ctx.exception))

    def test_statistical_overlays_match_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_2_stat_overlays.png"
        with tempfile.TemporaryDirectory(prefix="bridge_stat_overlay_baseline_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = self._write_overlay_csv(tmpdir_path, "overlay.csv")
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "overlay.png"),
                plot_type="scatter",
                x_column="strain",
                y_column="stress",
                title="Statistical overlays",
                fit_line=True,
                ci_band=True,
                significance_markers=({"x1": 1.0, "x2": 4.0, "y": 5.6, "label": "p<0.01"},),
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))

    def test_multi_series_legend_uses_standard_props(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            series_column="series",
            legend_layout="standard",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "S1", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "S1", "yerr": None},
            {"x": 0.0, "y": 1.5, "label": "", "series": "S2", "yerr": None},
            {"x": 1.0, "y": 2.5, "label": "", "series": "S2", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            # Standard layout has frameon=False and specific loc
            self.assertFalse(legend.get_frame_on())
            # 'best' location is 0 in matplotlib internals
            self.assertEqual(legend._loc, 0)
        finally:
            plt.close(fig)

    def test_smart_legend_avoids_data_points(self):
        # 1. 상단에 데이터가 몰려있는 경우 (범례는 하단으로 가야 함)
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="smart",
            series_column="series",
            legend_layout="smart",
        )
        # 상단 (y=0.8~1.0)에 데이터 집중
        points = [{"x": x / 10, "y": 0.9, "label": "", "series": "S1", "yerr": None} for x in range(10)] + [
            {"x": x / 10, "y": 0.1, "label": "", "series": "S2", "yerr": None}
            for x in range(2)  # 하단은 듬성듬성
        ]

        fig, ax = plt.subplots()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        try:
            _render_xy_plot(ax, points, spec, line=False)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)

            # bbox_to_anchor 확인 (Axes 좌표계 0~1)
            # 상단(y=0.9)에 데이터가 많으므로 범례는 하단(y < 0.5)으로 가야 함
            bbox = legend.get_bbox_to_anchor().transformed(ax.transAxes.inverted())
            self.assertLess(bbox.y0 + bbox.height / 2, 0.5)
        finally:
            plt.close(fig)

    def test_auto_legend_relocates_when_it_collides_with_data_in_nature(self):
        fig, ax, saved_rc = self._render_bridge_like_axes(self._cross_track_collision_points(), "nature")
        try:
            result = diagnose_figure_geometry(fig, [ax], layout_locked=False)
            legend_check = _legend_diagnostic(result)
            title_check = _geometry_check(result, "axis_label_title_overlap")
            artist_check = _geometry_check(result, "artist_overlaps")

            self.assertTrue(legend_check["passed"], legend_check)
            self.assertLessEqual(legend_check["data"]["overlap_frac"], 0.05)
            self.assertTrue(title_check["passed"], title_check)
            self.assertTrue(artist_check["passed"], artist_check)
        finally:
            self._close_bridge_like_axes(fig, saved_rc)

    def test_auto_legend_relocates_when_it_collides_with_data_in_compact_science(self):
        fig, ax, saved_rc = self._render_bridge_like_axes(self._cross_track_collision_points(), "science")
        try:
            result = diagnose_figure_geometry(fig, [ax], layout_locked=False)
            legend_check = _legend_diagnostic(result)
            title_check = _geometry_check(result, "axis_label_title_overlap")
            artist_check = _geometry_check(result, "artist_overlaps")

            self.assertTrue(legend_check["passed"], legend_check)
            self.assertLessEqual(legend_check["data"]["overlap_frac"], 0.05)
            self.assertTrue(title_check["passed"], title_check)
            self.assertTrue(artist_check["passed"], artist_check)
        finally:
            self._close_bridge_like_axes(fig, saved_rc)

    def test_auto_legend_keeps_already_clear_inside_placement(self):
        saved_rc = plt.rcParams.copy()
        apply_journal_theme("nature")
        fig, ax = plt.subplots(figsize=_figsize_for_format("nature"))
        try:
            ax.scatter([0.1, 0.2, 0.3], [0.1, 0.12, 0.14], label="low")
            ax.scatter([0.1, 0.2, 0.3], [0.25, 0.27, 0.29], label="mid")
            ax.set_xlim(0.0, 1.0)
            ax.set_ylim(0.0, 1.0)
            ax.legend(loc="upper right", frameon=False)
            before_loc = ax.get_legend()._loc
            spec = BridgeFigureSpec(
                csv_path="unused.csv",
                output_path="unused.png",
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="Clear inside legend",
                series_column="series",
                target_format="nature",
            )

            placement = _avoid_smart_legend_data_collision(fig, ax, spec)
            result = diagnose_figure_geometry(fig, [ax], layout_locked=False)
            legend_check = _legend_diagnostic(result)

            self.assertEqual(placement, "inside")
            self.assertEqual(ax.get_legend()._loc, before_loc)
            self.assertTrue(legend_check["passed"], legend_check)
            self.assertLessEqual(legend_check["data"]["overlap_frac"], 0.05)
            self.assertTrue(_legend_is_inside_axes(fig, ax))
        finally:
            plt.rcParams.update(saved_rc)
            plt.close(fig)

    def test_ppt_multi_series_legend_uses_right_outside_layout(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            series_column="series",
            target_format="ppt",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "S1", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "S1", "yerr": None},
            {"x": 0.0, "y": 1.5, "label": "", "series": "S2", "yerr": None},
            {"x": 1.0, "y": 2.5, "label": "", "series": "S2", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            _apply_layout(fig, ax, spec)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertFalse(legend.get_frame_on())
            self.assertEqual(legend._loc, 6)
            self.assertAlmostEqual(fig.subplotpars.right, 0.75, places=2)
            self.assertFalse(hasattr(fig, "_graph_hub_layout_lock"))
        finally:
            plt.close(fig)

    def test_best_legend_layout_overrides_ppt_default(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            series_column="series",
            target_format="ppt",
            legend_layout="best",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "S1", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "S1", "yerr": None},
            {"x": 0.0, "y": 1.5, "label": "", "series": "S2", "yerr": None},
            {"x": 1.0, "y": 2.5, "label": "", "series": "S2", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            _apply_layout(fig, ax, spec)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(_resolved_legend_layout(spec), "best")
            self.assertEqual(legend._loc, 0)
            self.assertGreater(fig.subplotpars.right, 0.9)
        finally:
            plt.close(fig)

    def test_standard_legend_layout_uses_standard_subplot_preset(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            series_column="series",
            legend_layout="standard",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "S1", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "S1", "yerr": None},
            {"x": 0.0, "y": 1.5, "label": "", "series": "S2", "yerr": None},
            {"x": 1.0, "y": 2.5, "label": "", "series": "S2", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            _apply_layout(fig, ax, spec)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(_resolved_legend_layout(spec), "standard")
            self.assertEqual(legend._loc, 0)
            fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
            pos = ax.get_position()
            self.assertAlmostEqual(fig_w_mm * pos.width, 70.0, places=1)
            self.assertAlmostEqual(fig_h_mm * pos.height, 55.0, places=1)
        finally:
            plt.close(fig)

    def test_legend_axis_polish_controls_reach_matplotlib_state(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            series_column="series",
            legend_layout="top_outside",
            legend_options={"title": "Treatment", "order": ("Alpha", "Beta"), "ncol": 2},
            series_styles={"Alpha": {"label": "display A"}, "Beta": {"label": "display B"}},
            axis_limits={"x": {"min": 0.0, "max": 1.0}, "y": {"min": 0.0, "max": 5.0}},
            tick_style={"rotation": 45.0, "format": "plain"},
        )
        points = [
            {"x": 0.0, "y": 3.0, "label": "", "series": "Beta", "yerr": None},
            {"x": 1.0, "y": 4.0, "label": "", "series": "Beta", "yerr": None},
            {"x": 0.0, "y": 1.0, "label": "", "series": "Alpha", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "Alpha", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            _apply_layout(fig, ax, spec)
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(legend.get_title().get_text(), "Treatment")
            self.assertEqual([text.get_text() for text in legend.get_texts()], ["display A", "display B"])
            self.assertEqual(legend._ncols, 2)
            self.assertEqual(ax.get_xlim(), (0.0, 1.0))
            self.assertEqual(ax.get_ylim(), (0.0, 5.0))
            self.assertTrue(all(label.get_rotation() == 45.0 for label in ax.get_xticklabels()))
            self.assertFalse(ax.xaxis.get_major_formatter().get_useOffset())
            self.assertFalse(ax.yaxis.get_major_formatter().get_useOffset())
        finally:
            plt.close(fig)

    def test_standard_layout_without_legend_still_uses_fixed_box(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            legend_layout="standard",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            self.assertIsNone(ax.get_legend())
            _apply_layout(fig, ax, spec)
            fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
            pos = ax.get_position()
            self.assertAlmostEqual(fig_w_mm * pos.width, 70.0, places=1)
            self.assertAlmostEqual(fig_h_mm * pos.height, 55.0, places=1)
        finally:
            plt.close(fig)

    def test_top_outside_layout_without_legend_still_uses_fixed_box(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="line",
            legend_layout="top_outside",
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=True)
            self.assertIsNone(ax.get_legend())
            _apply_layout(fig, ax, spec)
            fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
            pos = ax.get_position()
            self.assertAlmostEqual(fig_w_mm * pos.width, 70.0, places=1)
            self.assertAlmostEqual(fig_h_mm * pos.height, 55.0, places=1)
        finally:
            plt.close(fig)

    def test_top_outside_legend_with_title_has_clear_chrome_geometry(self):
        with tempfile.TemporaryDirectory(prefix="bridge_top_legend_title_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "multi_series.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = DictWriter(handle, fieldnames=["x", "y", "series"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"x": 0, "y": 1.0, "series": "Alpha"},
                        {"x": 1, "y": 1.8, "series": "Alpha"},
                        {"x": 0, "y": 1.4, "series": "Beta"},
                        {"x": 1, "y": 2.2, "series": "Beta"},
                        {"x": 0, "y": 1.8, "series": "Gamma"},
                        {"x": 1, "y": 2.6, "series": "Gamma"},
                    ]
                )
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "multi_series.png"),
                plot_type="line",
                x_column="x",
                y_column="y",
                title="Multi-series xy",
                series_column="series",
                legend_layout="top_outside",
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax = fig.axes[0]
                fig.canvas.draw()
                observed["geometry"] = diagnose_figure_geometry(
                    fig,
                    [ax],
                    layout_locked=hasattr(fig, "_graph_hub_layout_lock"),
                )
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                render_bridge_figure(spec)

            artist_check = _geometry_check(observed["geometry"], "artist_overlaps")
            legend_title_pairs = [
                pair
                for pair in artist_check["data"]["overlaps"]
                if {pair["a"].split(":", 1)[0], pair["b"].split(":", 1)[0]} == {"legend", "title"}
            ]
            self.assertEqual([], legend_title_pairs)
            self.assertTrue(_geometry_check(observed["geometry"], "axis_label_title_overlap")["passed"])

    def test_broken_axis_top_outside_legend_with_title_has_clear_chrome_geometry(self):
        with tempfile.TemporaryDirectory(prefix="bridge_broken_top_legend_title_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "broken_series.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = DictWriter(handle, fieldnames=["x", "y", "series"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"x": 1, "y": 10, "series": "Alpha"},
                        {"x": 2, "y": 18, "series": "Alpha"},
                        {"x": 3, "y": 22, "series": "Alpha"},
                        {"x": 1, "y": 900, "series": "Beta"},
                        {"x": 2, "y": 940, "series": "Beta"},
                        {"x": 3, "y": 970, "series": "Beta"},
                        {"x": 1, "y": 920, "series": "Gamma"},
                        {"x": 2, "y": 960, "series": "Gamma"},
                        {"x": 3, "y": 990, "series": "Gamma"},
                    ]
                )
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "broken_series.png"),
                plot_type="line",
                x_column="x",
                y_column="y",
                title="Broken-axis response",
                series_column="series",
                legend_layout="top_outside",
                y_break_range=(100.0, 800.0),
            )
            observed = {}

            def capture_figure(fig, output_path):
                ax_top = [ax for ax in fig.axes if ax.get_visible()][0]
                fig.canvas.draw()
                observed["geometry"] = diagnose_figure_geometry(
                    fig,
                    [ax_top],
                    layout_locked=hasattr(fig, "_graph_hub_layout_lock"),
                )
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                render_bridge_figure(spec)

            artist_check = _geometry_check(observed["geometry"], "artist_overlaps")
            legend_title_pairs = [
                pair
                for pair in artist_check["data"]["overlaps"]
                if {pair["a"].split(":", 1)[0], pair["b"].split(":", 1)[0]} == {"legend", "title"}
            ]
            self.assertEqual([], legend_title_pairs)
            self.assertTrue(_geometry_check(observed["geometry"], "axis_label_title_overlap")["passed"])

    def test_multipanel_bridge_panels_do_not_override_composite_canvas(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            right_csv = self._write_xy_csv(tmpdir_path, "right.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                        legend_layout="standard",
                    ),
                    BridgeFigureSpec(
                        csv_path=str(right_csv),
                        output_path=str(tmpdir_path / "right.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="right",
                        legend_layout="top_outside",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=2,
                column_width="double",
                panel_height_mm=65.0,
            )

            with patch("plotting.bridge_renderer.save_journal_fig") as mock_save:
                from plotting.bridge_renderer import render_multipanel_figure

                render_multipanel_figure(spec)

            fig = mock_save.call_args.args[0]
            fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(fig_w_mm, 180.0, places=1)
            self.assertAlmostEqual(fig_h_mm, 65.0, places=1)
            self.assertFalse(hasattr(fig, "_graph_hub_layout_lock"))

    def test_multipanel_manuscript_mode_preserves_panel_box_geometry(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_manuscript_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            right_csv = self._write_xy_csv(tmpdir_path, "right.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                        legend_layout="standard",
                    ),
                    BridgeFigureSpec(
                        csv_path=str(right_csv),
                        output_path=str(tmpdir_path / "right.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="right",
                        legend_layout="top_outside",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=2,
                column_width="double",
                panel_height_mm=65.0,
                compose_mode="manuscript",
            )

            with patch("plotting.bridge_renderer.save_journal_fig") as mock_save:
                from plotting.bridge_renderer import render_multipanel_figure

                render_multipanel_figure(spec)

            fig = mock_save.call_args.args[0]
            axes = [ax for ax in fig.axes if ax.get_visible()]
            self.assertEqual(len(axes), 2)
            fig_w_mm, fig_h_mm = (value * 25.4 for value in fig.get_size_inches())
            self.assertAlmostEqual(fig_w_mm, 180.0, places=1)
            self.assertAlmostEqual(fig_h_mm, 65.0, places=1)
            self.assertTrue(hasattr(fig, "_graph_hub_layout_lock"))
            for ax in axes:
                pos = ax.get_position()
                self.assertAlmostEqual(fig_w_mm * pos.width, 70.0, places=1)
                self.assertAlmostEqual(fig_h_mm * pos.height, 55.0, places=1)

    def test_multipanel_manuscript_mode_rejects_oversized_slot(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_small_slot_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                        legend_layout="standard",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=1,
                column_width="single",
                panel_height_mm=50.0,
                compose_mode="manuscript",
            )

            from plotting.bridge_renderer import render_multipanel_figure

            with self.assertRaisesRegex(ValueError, "panel box to fit within its slot"):
                render_multipanel_figure(spec)

    def test_multipanel_rejects_unknown_compose_mode(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_invalid_mode_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=1,
                compose_mode="final",
            )

            from plotting.bridge_renderer import render_multipanel_figure

            with self.assertRaisesRegex(ValueError, "unsupported compose_mode"):
                render_multipanel_figure(spec)

    def test_multipanel_rejects_negative_gutter(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_negative_gutter_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=1,
                compose_mode="manuscript",
                gutter_h_mm=-1.0,
            )

            from plotting.bridge_renderer import render_multipanel_figure

            with self.assertRaisesRegex(ValueError, "gutter_h_mm and gutter_v_mm must be non-negative"):
                render_multipanel_figure(spec)

    def test_multipanel_manuscript_mode_rejects_ppt_target_format(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_ppt_manuscript_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=1,
                target_format="ppt",
                compose_mode="manuscript",
            )

            from plotting.bridge_renderer import render_multipanel_figure

            with self.assertRaisesRegex(ValueError, "not supported for target_format='ppt'"):
                render_multipanel_figure(spec)

    def test_multipanel_manuscript_mode_rejects_non_fixed_layout_panel(self):
        with tempfile.TemporaryDirectory(prefix="bridge_multi_smart_panel_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            left_csv = self._write_xy_csv(tmpdir_path, "left.csv")
            spec = MultiPanelSpec(
                panels=(
                    BridgeFigureSpec(
                        csv_path=str(left_csv),
                        output_path=str(tmpdir_path / "left.png"),
                        plot_type="line",
                        x_column="x",
                        y_column="y",
                        title="left",
                        legend_layout="best",
                    ),
                ),
                output_path=str(tmpdir_path / "multi.png"),
                rows=1,
                cols=1,
                panel_height_mm=65.0,
                compose_mode="manuscript",
            )

            from plotting.bridge_renderer import render_multipanel_figure

            with self.assertRaisesRegex(ValueError, "requires fixed-layout panels"):
                render_multipanel_figure(spec)

    def test_annotations_use_compressed_labels(self):
        fig, ax = plt.subplots()
        try:
            _annotate_points(
                ax,
                xs=[0.0],
                ys=[1.0],
                labels=["Coated Sample_Noa_None_Aligned"],
                compress_labels=True,
            )
            self.assertEqual(len(ax.texts), 1)
            self.assertEqual(ax.texts[0].get_text(), "Coated, Noa, None, Aln.")
        finally:
            plt.close(fig)

    def test_annotations_can_preserve_labels(self):
        fig, ax = plt.subplots()
        try:
            _annotate_points(
                ax,
                xs=[0.0],
                ys=[1.0],
                labels=["Coated Sample_Noa_None_Aligned"],
                compress_labels=False,
            )
            self.assertEqual(len(ax.texts), 1)
            self.assertEqual(ax.texts[0].get_text(), "Coated Sample_Noa_None_Aligned")
        finally:
            plt.close(fig)

    def test_annotation_overlay_contrast_diagnostic_from_renderer_tags(self):
        fig, ax = plt.subplots(figsize=(3, 3))
        try:
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            spec = BridgeFigureSpec(
                csv_path="unused.csv",
                output_path="unused.png",
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="contrast",
                annotations=({"hspan": {"ymin": 0.2, "ymax": 0.8}, "text": "dark", "color": "black", "alpha": 0.9},),
            )
            _draw_annotations(ax, spec)

            check = _geometry_check(
                diagnose_figure_geometry(fig, [ax], layout_locked=False),
                "annotation_overlay_contrast",
            )

            self.assertFalse(check["passed"])
            self.assertEqual(check["data"]["pairs"][0]["overlay_role"], "annotation_hspan")
        finally:
            plt.close(fig)

    def test_point_label_options_limit_by_priority_and_report_skips(self):
        fig, ax = plt.subplots()
        try:
            points = [
                {"raw": {"priority": "1", "hide": "0"}},
                {"raw": {"priority": "5", "hide": "0"}},
                {"raw": {"priority": "3", "hide": "yes"}},
            ]
            _annotate_points(
                ax,
                xs=[0.0, 1.0, 2.0],
                ys=[1.0, 2.0, 3.0],
                labels=["low", "high", "hidden"],
                compress_labels=False,
                point_label_options={
                    "max_labels": 1,
                    "priority_column": "priority",
                    "skip_column": "hide",
                    "fanout": "compass",
                },
                points=points,
            )
            self.assertEqual([text.get_text() for text in ax.texts], ["high"])
            self.assertEqual(ax.texts[0].xyann, (8.0, 8.0))
            result = diagnose_figure_geometry(fig, [ax], layout_locked=False)
            check = _geometry_check(result, "point_label_skips")
            self.assertFalse(check["passed"])
            self.assertEqual(check["data"]["skipped_labels"], 2)
            self.assertEqual(check["data"]["reasons"], {"skip_column": 1, "max_labels": 1})
        finally:
            plt.close(fig)

    def test_point_label_options_static_offset(self):
        fig, ax = plt.subplots()
        try:
            _annotate_points(
                ax,
                xs=[0.0],
                ys=[1.0],
                labels=["S1"],
                compress_labels=False,
                point_label_options={"offset": {"dx": 3, "dy": 7}},
                points=[{"raw": {}}],
            )
            self.assertEqual(ax.texts[0].xyann, (3.0, 7.0))
        finally:
            plt.close(fig)

    def test_point_label_max_labels_applies_across_series(self):
        fig, ax = plt.subplots()
        try:
            spec = BridgeFigureSpec(
                csv_path="unused.csv",
                output_path="unused.png",
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="labels",
                label_column="label",
                series_column="series",
                point_label_options={"max_labels": 1, "priority_column": "priority"},
            )
            points = [
                {"x": 0.0, "y": 1.0, "label": "low-a", "series": "A", "raw": {"priority": "1"}},
                {"x": 1.0, "y": 2.0, "label": "high-b", "series": "B", "raw": {"priority": "5"}},
            ]
            _render_xy_plot(ax, points, spec, line=False)
            self.assertEqual([text.get_text() for text in ax.texts], ["high-b"])
            check = _geometry_check(diagnose_figure_geometry(fig, [ax], layout_locked=False), "point_label_skips")
            self.assertEqual(check["data"]["skipped_labels"], 1)
        finally:
            plt.close(fig)

    def test_errorbar_cap_width_applied(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="cap_test",
            yerr_column="err",
            yerr_cap_width=6.0,
        )
        points = [
            {"x": 0.0, "y": 1.0, "label": "", "series": "", "yerr": 0.1, "yerr_minus": None},
            {"x": 1.0, "y": 2.0, "label": "", "series": "", "yerr": 0.2, "yerr_minus": None},
        ]

        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=False)
            # errorbar containers hold the caplines
            eb_containers = [c for c in ax.containers if hasattr(c, "lines")]
            self.assertTrue(len(eb_containers) > 0)
            # Verify errorbar was rendered with cap lines present
            caplines = eb_containers[0].lines[1]
            self.assertTrue(len(caplines) > 0, "Expected cap lines in errorbar")
        finally:
            plt.close(fig)

    def test_asymmetric_errorbar(self):
        import numpy as np

        with tempfile.TemporaryDirectory(prefix="bridge_asym_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "asym.csv"
            csv_path.write_text("x,y,err_plus,err_minus\n0,1.0,0.3,0.1\n1,2.0,0.4,0.2\n", encoding="utf-8")

            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(tmpdir_path / "out.png"),
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="asym_test",
                yerr_column="err_plus",
                yerr_minus_column="err_minus",
            )

            from plotting.bridge_renderer import _load_points, _yerr_values

            points = _load_points(csv_path, spec)
            self.assertEqual(len(points), 2)
            yerr = _yerr_values(points, spec)
            self.assertIsNotNone(yerr)
            self.assertEqual(yerr.shape, (2, 2))
            np.testing.assert_array_almost_equal(yerr[0], [0.1, 0.2])
            np.testing.assert_array_almost_equal(yerr[1], [0.3, 0.4])

    def test_axes_metadata_uses_override_labels_when_present(self):
        spec = BridgeFigureSpec(
            csv_path="unused.csv",
            output_path="unused.png",
            plot_type="bar",
            x_column="x",
            y_column="y",
            title="title",
            x_axis_label="Metric",
            y_axis_label="Response",
        )

        fig, ax = plt.subplots()
        try:
            _apply_axes_metadata(ax, spec)
            self.assertEqual(ax.get_xlabel(), "Metric")
            self.assertEqual(ax.get_ylabel(), "Response")
        finally:
            plt.close(fig)


class SeriesStyleOverrideTest(unittest.TestCase):
    def test_render_xy_plot_applies_series_marker_fill_and_edge_overrides(self):
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            series_column="series",
            series_styles={
                "Reference": {"marker": "o", "fill": "none", "edgecolor": "black"},
                "This work": {"marker": "s", "facecolor": "#1f77b4", "edgecolor": "#1f77b4"},
            },
        )
        points = [
            {"x": 1.0, "y": 2.0, "series": "Reference", "label": ""},
            {"x": 2.0, "y": 3.0, "series": "This work", "label": ""},
        ]
        ax = MagicMock()
        ax.margins.return_value = (0.05, 0.05)

        _render_xy_plot(ax, points, spec, line=False)

        self.assertEqual(ax.scatter.call_count, 2)
        reference_call = ax.scatter.call_args_list[0]
        this_work_call = ax.scatter.call_args_list[1]
        self.assertEqual(reference_call.kwargs["marker"], "o")
        self.assertEqual(reference_call.kwargs["facecolors"], "none")
        self.assertEqual(reference_call.kwargs["edgecolors"], "black")
        self.assertEqual(this_work_call.kwargs["marker"], "s")
        self.assertEqual(this_work_call.kwargs["facecolors"], "#1f77b4")
        self.assertEqual(this_work_call.kwargs["edgecolors"], "#1f77b4")

    def test_render_xy_plot_applies_series_styles_to_errorbar_markers(self):
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            series_column="series",
            yerr_column="err",
            series_styles={"Reference": {"marker": "D", "fill": "none", "edgecolor": "black"}},
        )
        points = [
            {"x": 1.0, "y": 2.0, "yerr": 0.1, "yerr_minus": None, "series": "Reference", "label": ""},
        ]
        ax = MagicMock()
        ax.margins.return_value = (0.05, 0.05)

        _render_xy_plot(ax, points, spec, line=False)

        ax.errorbar.assert_called_once()
        self.assertEqual(ax.errorbar.call_args.kwargs["fmt"], "D")
        self.assertEqual(ax.errorbar.call_args.kwargs["markerfacecolor"], "none")
        self.assertEqual(ax.errorbar.call_args.kwargs["markeredgecolor"], "black")

    def test_render_xy_plot_applies_series_visual_hierarchy_overrides(self):
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            series_column="series",
            series_styles={
                "Reference": {
                    "color": "#888888",
                    "alpha": "0.35",
                    "size": "18",
                    "zorder": "2",
                    "label": "Literature",
                },
                "This work": {
                    "color": "#1f77b4",
                    "alpha": "1",
                    "size": "42",
                    "zorder": "5",
                    "label": "This work",
                },
            },
        )
        points = [
            {"x": 1.0, "y": 2.0, "series": "Reference", "label": ""},
            {"x": 2.0, "y": 3.0, "series": "This work", "label": ""},
        ]
        ax = MagicMock()
        ax.margins.return_value = (0.05, 0.05)

        _render_xy_plot(ax, points, spec, line=False)

        reference_call = ax.scatter.call_args_list[0]
        this_work_call = ax.scatter.call_args_list[1]
        self.assertNotIn("c", reference_call.kwargs)
        self.assertEqual(reference_call.kwargs["facecolors"], "#888888")
        self.assertEqual(reference_call.kwargs["edgecolors"], "#888888")
        self.assertEqual(reference_call.kwargs["alpha"], 0.35)
        self.assertEqual(reference_call.kwargs["s"], 18.0)
        self.assertEqual(reference_call.kwargs["zorder"], 2.0)
        self.assertEqual(reference_call.kwargs["label"], "Literature")
        self.assertNotIn("c", this_work_call.kwargs)
        self.assertEqual(this_work_call.kwargs["facecolors"], "#1f77b4")
        self.assertEqual(this_work_call.kwargs["edgecolors"], "#1f77b4")
        self.assertEqual(this_work_call.kwargs["alpha"], 1.0)
        self.assertEqual(this_work_call.kwargs["s"], 42.0)
        self.assertEqual(this_work_call.kwargs["zorder"], 5.0)
        self.assertEqual(this_work_call.kwargs["label"], "This work")

    def test_render_xy_plot_applies_line_visual_hierarchy_overrides(self):
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="line",
            x_column="x",
            y_column="y",
            title="t",
            series_column="series",
            series_styles={
                "A": {
                    "color": "#444444",
                    "alpha": "0.6",
                    "linewidth": "2.4",
                    "size": "6",
                    "zorder": "3",
                    "label": "Series A",
                }
            },
        )
        points = [
            {"x": 1.0, "y": 2.0, "series": "A", "label": ""},
            {"x": 2.0, "y": 3.0, "series": "A", "label": ""},
        ]
        ax = MagicMock()
        ax.margins.return_value = (0.05, 0.05)

        _render_xy_plot(ax, points, spec, line=True)

        ax.plot.assert_called_once()
        kwargs = ax.plot.call_args.kwargs
        self.assertEqual(kwargs["color"], "#444444")
        self.assertEqual(kwargs["markerfacecolor"], "#444444")
        self.assertEqual(kwargs["markeredgecolor"], "#444444")
        self.assertEqual(kwargs["alpha"], 0.6)
        self.assertEqual(kwargs["linewidth"], 2.4)
        self.assertEqual(kwargs["markersize"], 6.0)
        self.assertEqual(kwargs["zorder"], 3.0)
        self.assertEqual(kwargs["label"], "Series A")


class AnnotationStyleTest(unittest.TestCase):
    def setUp(self):
        self._saved_rc = plt.rcParams.copy()

    def tearDown(self):
        plt.rcParams.update(self._saved_rc)

    def test_annotation_font_size_uses_style_token_not_default(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        size = _annotation_font_size()
        self.assertAlmostEqual(size, float(plt.rcParams["xtick.labelsize"]))
        # Regression: previously inherited matplotlib's 10 pt default and tripped
        # the font_size_token_drift geometry check.
        self.assertLess(size, 10.0)

    def test_draw_annotations_apply_token_fontsize_and_clip(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        expected = _annotation_font_size()
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {"x": 1.0, "y": 2.0, "text": "plain"},
                {"x": 1.0, "y": 2.0, "text": "arrow", "arrow_to": {"x": 3.0, "y": 4.0}},
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        self.assertEqual(ax.text.call_count, 1)
        self.assertAlmostEqual(ax.text.call_args.kwargs["fontsize"], expected)
        self.assertTrue(ax.text.call_args.kwargs["clip_on"])

        self.assertEqual(ax.annotate.call_count, 1)
        self.assertAlmostEqual(ax.annotate.call_args.kwargs["fontsize"], expected)
        self.assertTrue(ax.annotate.call_args.kwargs["clip_on"])

    def test_draw_annotations_renders_region_span_with_label(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {
                    "region": {"xmin": 1e9, "xmax": 1e12, "ymin": 15.0, "ymax": 50.0},
                    "text": "TARGET",
                    "color": "#3b7d3b",
                    "alpha": 0.15,
                },
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        self.assertEqual(ax.fill_between.call_count, 1)
        span_args = ax.fill_between.call_args.args
        self.assertEqual(span_args[0], [1e9, 1e12])
        self.assertEqual((span_args[1], span_args[2]), (15.0, 50.0))
        self.assertAlmostEqual(ax.fill_between.call_args.kwargs["alpha"], 0.15)
        # centered label uses the token font size, not the 10 pt default
        self.assertEqual(ax.text.call_count, 1)
        self.assertEqual(ax.text.call_args.args[2], "TARGET")
        self.assertAlmostEqual(ax.text.call_args.kwargs["fontsize"], _annotation_font_size())

    def test_draw_annotations_renders_curved_arrow_without_text(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {
                    "x": 2.0,
                    "y": 200.0,
                    "text": "",
                    "arrow_to": {"x": 1.0, "y": 20.0},
                    "arrowstyle": "-|>",
                    "connectionstyle": "arc3,rad=0.25",
                    "color": "black",
                },
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        self.assertEqual(ax.annotate.call_count, 1)
        call = ax.annotate.call_args
        self.assertEqual(call.args[0], "")
        self.assertEqual(call.kwargs["xy"], (1.0, 20.0))
        self.assertEqual(call.kwargs["xytext"], (2.0, 200.0))
        self.assertEqual(call.kwargs["arrowprops"]["arrowstyle"], "-|>")
        self.assertEqual(call.kwargs["arrowprops"]["connectionstyle"], "arc3,rad=0.25")
        self.assertTrue(call.kwargs["clip_on"])

    def test_draw_annotations_uses_explicit_callout_offset_points(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {
                    "x": 2.0,
                    "y": 200.0,
                    "text": "offset",
                    "arrow_to": {"x": 1.0, "y": 20.0},
                    "xytext_offset": {"dx": 12, "dy": 18},
                    "color": "black",
                },
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        call = ax.annotate.call_args
        self.assertEqual(call.kwargs["xy"], (1.0, 20.0))
        self.assertEqual(call.kwargs["xytext"], (12.0, 18.0))
        self.assertEqual(call.kwargs["textcoords"], "offset points")

    def test_draw_annotations_uses_preset_and_avoid_overlap_offsets(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {"x": 1.0, "y": 1.0, "text": "a", "placement_preset": "upper_right"},
                {"x": 1.0, "y": 1.0, "text": "b", "avoid_overlap": True},
                {"x": 1.0, "y": 1.0, "text": "c", "avoid_overlap": True},
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        offsets = [call.kwargs["xytext"] for call in ax.annotate.call_args_list]
        self.assertEqual(offsets[0], (8.0, 8.0))
        self.assertNotEqual(offsets[1], offsets[2])
        self.assertTrue(all(call.kwargs["textcoords"] == "offset points" for call in ax.annotate.call_args_list))

    def test_draw_annotations_preserves_legacy_data_coordinate_arrow_position(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {"x": 2.0, "y": 200.0, "text": "legacy", "arrow_to": {"x": 1.0, "y": 20.0}},
            ),
        )
        ax = MagicMock()
        _draw_annotations(ax, spec)

        call = ax.annotate.call_args
        self.assertEqual(call.kwargs["xytext"], (2.0, 200.0))
        self.assertNotIn("textcoords", call.kwargs)

    def test_draw_annotations_rejects_callout_offset_on_region(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {
                    "region": {"xmin": 1, "xmax": 2, "ymin": 10, "ymax": 20},
                    "xytext_offset": {"dx": 12, "dy": 18},
                },
            ),
        )

        with self.assertRaisesRegex(ValueError, "only apply to point annotations"):
            _draw_annotations(MagicMock(), spec)

    def test_draw_annotations_renders_hspan_and_vspan(self):
        apply_journal_theme(target_format="nature", profile_name="baseline")
        spec = BridgeFigureSpec(
            csv_path="x.csv",
            output_path="out.png",
            plot_type="scatter",
            x_column="x",
            y_column="y",
            title="t",
            annotations=(
                {"hspan": {"ymin": 10.0, "ymax": 1000.0}, "text": "band", "color": "#ccc", "alpha": 0.4},
                {"vspan": {"xmin": 1.0, "xmax": 100.0}, "text": "window", "color": "#ddd"},
            ),
        )
        ax = MagicMock()
        y_transform = object()
        x_transform = object()
        ax.get_yaxis_transform.return_value = y_transform
        ax.get_xaxis_transform.return_value = x_transform
        _draw_annotations(ax, spec)

        ax.axhspan.assert_called_once_with(10.0, 1000.0, color="#ccc", alpha=0.4, linewidth=0, zorder=0)
        ax.axvspan.assert_called_once_with(1.0, 100.0, color="#ddd", alpha=0.12, linewidth=0, zorder=0)
        self.assertEqual(ax.text.call_count, 2)
        self.assertEqual(ax.text.call_args_list[0].args[0], 0.5)
        self.assertEqual(ax.text.call_args_list[0].args[2], "band")
        self.assertIs(ax.text.call_args_list[0].kwargs["transform"], y_transform)
        self.assertEqual(ax.text.return_value._graph_hub_annotation_text_role, "annotation_vspan")
        self.assertEqual(ax.text.call_args_list[1].args[2], "window")
        self.assertEqual(ax.text.call_args_list[1].args[1], 0.5)
        self.assertIs(ax.text.call_args_list[1].kwargs["transform"], x_transform)

    def test_draw_manual_overlays_renders_guide_curve_and_fill_between_columns(self):
        with tempfile.TemporaryDirectory(prefix="bridge_manual_overlay_") as tmpdir:
            csv_path = Path(tmpdir) / "overlay.csv"
            csv_path.write_text("x,y,low,high\n1,10,8,12\n2,20,18,23\n", encoding="utf-8")
            ax = MagicMock()
            spec = BridgeFigureSpec(
                csv_path=str(csv_path),
                output_path=str(Path(tmpdir) / "out.png"),
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="manual overlays",
                guide_curves=(
                    {
                        "points": [{"x": 1, "y": 9}, {"x": 2, "y": 21}],
                        "color": "red",
                        "linestyle": "--",
                        "label": "guide",
                    },
                ),
                fill_between=(
                    {
                        "x_column": "x",
                        "y1_column": "low",
                        "y2_column": "high",
                        "color": "#dddddd",
                        "alpha": 0.25,
                    },
                ),
            )

            _draw_manual_overlays(ax, csv_path, spec)

            ax.fill_between.assert_called_once()
            self.assertEqual(ax.fill_between.call_args.args, ([1.0, 2.0], [8.0, 18.0], [12.0, 23.0]))
            self.assertEqual(ax.fill_between.call_args.kwargs["alpha"], 0.25)
            self.assertEqual(ax.fill_between.return_value._graph_hub_overlay_role, "fill_between")
            self.assertEqual(ax.fill_between.return_value._graph_hub_overlay_label, "fill_between[0]")
            ax.plot.assert_called_once()
            self.assertEqual(ax.plot.call_args.args, ([1.0, 2.0], [9.0, 21.0]))
            self.assertEqual(ax.plot.call_args.kwargs["linestyle"], "--")


if __name__ == "__main__":
    unittest.main()
