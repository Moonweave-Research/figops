"""Tests for bridge_renderer robustness features: NaN filtering, CSV validation, empty guard, timestamps."""

import csv
import hashlib
import os
import tempfile
import unittest
import warnings
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

from plotting.bridge_renderer import (
    BridgeFigureSpec,
    _deterministic_timestamp,
    _load_points,
    _render_plot,
    render_bridge_figure,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _make_spec(csv_path: str, **overrides) -> BridgeFigureSpec:
    defaults = dict(
        csv_path=csv_path,
        output_path="/tmp/test.png",
        plot_type="scatter",
        x_column="x",
        y_column="y",
        title="Test",
    )
    defaults.update(overrides)
    return BridgeFigureSpec(**defaults)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestYBreakRangeSupportedFields(unittest.TestCase):
    """Regression: y_break_range must preserve series/error-bar/label/overlay inputs."""

    def test_y_break_with_series_column_renders_instead_of_silent_collapse(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(csv_path, [{"x": "1", "y": "10", "s": "A"}, {"x": "2", "y": "900", "s": "B"}])
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                series_column="s",
                y_break_range=(100.0, 800.0),
            )
            out = render_bridge_figure(spec)
            self.assertTrue(Path(out).exists())

    def test_y_break_with_overlay_baselines_renders_on_top_axis(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(csv_path, [{"x": "1", "y": "10"}, {"x": "2", "y": "900"}])
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                overlay_baselines=({"label": "ref", "value": 850.0},),
                y_break_range=(100.0, 800.0),
            )

            observed = {}

            def capture_figure(fig, output_path):
                visible_axes = [ax for ax in fig.axes if ax.get_visible()]
                observed["baseline_lines"] = [
                    line
                    for line in visible_axes[0].lines
                    if line.get_linestyle() == "--" and list(line.get_ydata()) == [850.0, 850.0]
                ]
                observed["annotations"] = [text.get_text() for text in visible_axes[0].texts]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(len(observed["baseline_lines"]), 1)
            self.assertIn("ref", observed["annotations"])

    def test_y_break_with_series_yerr_labels_and_overlay_preserves_artists(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(
                csv_path,
                [
                    {"x": "1", "y": "10", "series": "Alpha", "err": "1.0", "label": "a-low"},
                    {"x": "2", "y": "16", "series": "Alpha", "err": "1.5", "label": "a-high"},
                    {"x": "1", "y": "900", "series": "Beta", "err": "25", "label": "b-low"},
                    {"x": "2", "y": "940", "series": "Beta", "err": "30", "label": "b-high"},
                ],
            )
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                plot_type="line",
                series_column="series",
                yerr_column="err",
                label_column="label",
                overlay_baselines=({"label": "target", "value": 920.0},),
                y_break_range=(100.0, 800.0),
                legend_layout="standard",
            )

            observed = {}

            def capture_figure(fig, output_path):
                ax_top, ax_bot = [ax for ax in fig.axes if ax.get_visible()]
                legend = ax_top.get_legend()
                observed["legend_labels"] = [text.get_text() for text in legend.get_texts()]
                observed["top_line_count"] = len(ax_top.lines)
                observed["bot_line_count"] = len(ax_bot.lines)
                observed["top_collections"] = len(ax_top.collections)
                observed["bot_collections"] = len(ax_bot.collections)
                observed["top_text"] = [text.get_text() for text in ax_top.texts]
                observed["bot_text"] = [text.get_text() for text in ax_bot.texts]
                Path(output_path).write_bytes(b"png")

            with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_figure):
                out = render_bridge_figure(spec)

            self.assertTrue(Path(out).exists())
            self.assertEqual(observed["legend_labels"], ["Alpha", "Beta"])
            self.assertGreaterEqual(observed["top_line_count"], 7)
            self.assertGreaterEqual(observed["bot_line_count"], 6)
            self.assertGreaterEqual(observed["top_collections"], 2)
            self.assertGreaterEqual(observed["bot_collections"], 2)
            self.assertIn("target", observed["top_text"])
            self.assertIn("a-low", observed["bot_text"])
            self.assertIn("b-low", observed["top_text"])

    def test_y_break_without_unsupported_fields_still_renders(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(
                csv_path,
                [{"x": "1", "y": "10"}, {"x": "2", "y": "900"}, {"x": "3", "y": "950"}],
            )
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                plot_type="scatter",
                y_break_range=(100.0, 800.0),
            )
            out = render_bridge_figure(spec)
            self.assertTrue(Path(out).exists())

    def test_multiseries_broken_axis_matches_visual_regression_baseline(self):
        baseline = Path(__file__).parent / "fixtures" / "visual_regression" / "m4_1_multiseries_broken_axis.png"
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(
                csv_path,
                [
                    {"x": "1", "y": "10", "series": "Alpha", "err": "1.0", "label": "a-low"},
                    {"x": "2", "y": "16", "series": "Alpha", "err": "1.5", "label": "a-high"},
                    {"x": "3", "y": "18", "series": "Alpha", "err": "1.2", "label": "a-peak"},
                    {"x": "1", "y": "900", "series": "Beta", "err": "25", "label": "b-low"},
                    {"x": "2", "y": "940", "series": "Beta", "err": "30", "label": "b-high"},
                    {"x": "3", "y": "970", "series": "Beta", "err": "20", "label": "b-peak"},
                ],
            )
            output_path = Path(td) / "out.png"
            spec = _make_spec(
                str(csv_path),
                output_path=str(output_path),
                plot_type="line",
                series_column="series",
                yerr_column="err",
                label_column="label",
                overlay_baselines=({"label": "target", "value": 940.0},),
                y_break_range=(100.0, 800.0),
                legend_layout="standard",
            )

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                out = render_bridge_figure(spec)

            self.assertTrue(baseline.exists(), f"missing visual baseline: {baseline}")
            self.assertEqual(_sha256(Path(out)), _sha256(baseline))


class TestLoadPointsNanFiltering(unittest.TestCase):
    def test_nan_rows_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(
                p,
                [
                    {"x": "1", "y": "10"},
                    {"x": "2", "y": "nan"},
                    {"x": "3", "y": "20"},
                ],
            )
            spec = _make_spec(str(p))
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                points = _load_points(p, spec)
                self.assertEqual(len(points), 2)
                self.assertEqual(len(w), 1)
                self.assertIn("1 row(s)", str(w[0].message))

    def test_inf_rows_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(
                p,
                [
                    {"x": "1", "y": "inf"},
                    {"x": "2", "y": "-inf"},
                    {"x": "3", "y": "5"},
                ],
            )
            spec = _make_spec(str(p))
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                points = _load_points(p, spec)
                self.assertEqual(len(points), 1)
                self.assertEqual(points[0]["y"], 5.0)
                self.assertGreater(len(w), 0)
                self.assertIn("NaN/inf", str(w[0].message))

    def test_clean_data_no_warning(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(
                p,
                [
                    {"x": "1", "y": "10"},
                    {"x": "2", "y": "20"},
                ],
            )
            spec = _make_spec(str(p))
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                points = _load_points(p, spec)
                self.assertEqual(len(points), 2)
                nan_warnings = [x for x in w if "NaN/inf" in str(x.message)]
                self.assertEqual(len(nan_warnings), 0)


class TestLoadPointsColumnValidation(unittest.TestCase):
    def test_missing_column_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(p, [{"a": "1", "b": "2"}])
            spec = _make_spec(str(p), x_column="x", y_column="y")
            with self.assertRaises(ValueError) as ctx:
                _load_points(p, spec)
            self.assertIn("x", str(ctx.exception))
            self.assertIn("y", str(ctx.exception))

    def test_valid_columns_no_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(p, [{"x": "1", "y": "2"}])
            spec = _make_spec(str(p))
            points = _load_points(p, spec)
            self.assertEqual(len(points), 1)


class TestEmptyDatasetGuard(unittest.TestCase):
    def test_empty_points_warns(self):
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        spec = _make_spec("/tmp/test.csv", title="Empty Test")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _render_plot(ax, [], spec)
            self.assertTrue(any("blank" in str(x.message) for x in w))
        plt.close(fig)


class TestAsymmetricLowerErrorNotDropped(unittest.TestCase):
    """Regression: a spec with only yerr_minus_column used to draw NO error bars."""

    def test_only_yerr_minus_produces_errorbars(self):
        import numpy as np

        from plotting.bridge_renderer import _yerr_values

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            _write_csv(
                p,
                [
                    {"x": "0", "y": "1.0", "err_minus": "0.1"},
                    {"x": "1", "y": "2.0", "err_minus": "0.2"},
                ],
            )
            spec = _make_spec(str(p), yerr_minus_column="err_minus")
            points = _load_points(p, spec)
            self.assertEqual(len(points), 2)
            yerr = _yerr_values(points, spec)
            self.assertIsNotNone(yerr)
            yerr_arr = np.asarray(yerr)
            self.assertEqual(yerr_arr.shape, (2, 2))
            np.testing.assert_array_almost_equal(yerr_arr[0], [0.1, 0.2])

    def test_only_yerr_minus_draws_errorbar_artist(self):
        import matplotlib.pyplot as plt

        from plotting.bridge_renderer import _render_xy_plot

        spec = _make_spec("unused.csv", yerr_minus_column="err_minus")
        points = [
            {"x": 0.0, "y": 1.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": 0.1},
            {"x": 1.0, "y": 2.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": 0.2},
        ]
        fig, ax = plt.subplots()
        try:
            _render_xy_plot(ax, points, spec, line=False)
            # errorbar adds LineCollection(s) for the bars; plain scatter would not.
            self.assertTrue(len(ax.collections) > 1 or len(ax.lines) > 0)
        finally:
            plt.close(fig)


class TestHeatmapZColumnGuard(unittest.TestCase):
    """Regression: heatmap with empty z_column rendered an all-NaN blank figure silently."""

    def test_empty_z_column_raises(self):
        import matplotlib.pyplot as plt

        from plotting.bridge_renderer import _render_plot

        spec = _make_spec("unused.csv", plot_type="heatmap", z_column="")
        points = [
            {"x": 0.0, "y": 0.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": None},
        ]
        fig, ax = plt.subplots()
        try:
            with self.assertRaises(ValueError):
                _render_plot(ax, points, spec)
        finally:
            plt.close(fig)

    def test_duplicate_cells_warn(self):
        import matplotlib.pyplot as plt

        from plotting.bridge_renderer import _render_heatmap_plot

        spec = _make_spec("unused.csv", plot_type="heatmap", z_column="z")
        points = [
            {"x": 0.0, "y": 0.0, "z": 1.0, "label": "", "series": "", "yerr": None, "yerr_minus": None},
            {"x": 0.0, "y": 0.0, "z": 5.0, "label": "", "series": "", "yerr": None, "yerr_minus": None},
            {"x": 1.0, "y": 1.0, "z": 3.0, "label": "", "series": "", "yerr": None, "yerr_minus": None},
        ]
        fig, ax = plt.subplots()
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _render_heatmap_plot(ax, points, spec)
                self.assertTrue(any("duplicate" in str(x.message).lower() for x in w))
        finally:
            plt.close(fig)


class TestSingleSeriesBarDuplicateCategories(unittest.TestCase):
    """Regression: single-series bar with duplicate categories silently overplots."""

    def test_duplicate_category_warns(self):
        import matplotlib.pyplot as plt

        from plotting.bridge_renderer import _render_bar_plot

        spec = _make_spec("unused.csv", plot_type="bar")
        points = [
            {"x": "A", "y": 1.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": None},
            {"x": "A", "y": 3.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": None},
            {"x": "B", "y": 2.0, "z": None, "label": "", "series": "", "yerr": None, "yerr_minus": None},
        ]
        fig, ax = plt.subplots()
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _render_bar_plot(ax, points, spec)
                self.assertTrue(any("duplicate" in str(x.message).lower() for x in w))
        finally:
            plt.close(fig)


class TestDeterministicTimestamp(unittest.TestCase):
    def test_source_date_epoch_override(self):
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        try:
            ts = _deterministic_timestamp()
            self.assertIn("1970-01-01", ts)
        finally:
            del os.environ["SOURCE_DATE_EPOCH"]

    def test_without_epoch_returns_current(self):
        os.environ.pop("SOURCE_DATE_EPOCH", None)
        ts = _deterministic_timestamp()
        self.assertIn("T", ts)  # ISO format contains T


if __name__ == "__main__":
    unittest.main()
