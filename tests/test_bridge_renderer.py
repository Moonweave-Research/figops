import hashlib
import os
import tempfile
import unittest
import warnings
from csv import DictWriter
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plotting.bridge_renderer import (
    BridgeFigureSpec,
    MultiPanelSpec,
    _annotate_points,
    _apply_axes_metadata,
    _apply_layout,
    _display_label,
    _render_bar_plot,
    _render_heatmap_plot,
    _render_xy_plot,
    _resolved_legend_layout,
    render_bridge_figure,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        points = [
            {"x": x/10, "y": 0.9, "label": "", "series": "S1", "yerr": None}
            for x in range(10)
        ] + [
            {"x": x/10, "y": 0.1, "label": "", "series": "S2", "yerr": None}
            for x in range(2) # 하단은 듬성듬성
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
            self.assertLess(bbox.y0 + bbox.height/2, 0.5)
        finally:
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
            self.assertAlmostEqual(fig_w_mm, 183.0, places=1)
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
            self.assertAlmostEqual(fig_w_mm, 183.0, places=1)
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


if __name__ == "__main__":
    unittest.main()
