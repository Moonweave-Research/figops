"""Tests for bridge_renderer robustness features: NaN filtering, CSV validation, empty guard, timestamps."""

import csv
import os
import tempfile
import unittest
import warnings

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


class TestYBreakRangeRejectsUnsupportedFields(unittest.TestCase):
    """Regression: y_break_range used to silently drop series/error-bar/label/overlay inputs."""

    def test_y_break_with_series_column_raises_instead_of_silent_collapse(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(csv_path, [{"x": "1", "y": "10", "s": "A"}, {"x": "2", "y": "900", "s": "B"}])
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                series_column="s",
                y_break_range=(100.0, 800.0),
            )
            with self.assertRaises(ValueError) as ctx:
                render_bridge_figure(spec)
            self.assertIn("y_break_range", str(ctx.exception))
            self.assertIn("series_column", str(ctx.exception))

    def test_y_break_with_overlay_baselines_raises(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "data.csv"
            _write_csv(csv_path, [{"x": "1", "y": "10"}, {"x": "2", "y": "900"}])
            spec = _make_spec(
                str(csv_path),
                output_path=str(Path(td) / "out.png"),
                overlay_baselines=({"label": "ref", "y": 5.0},),
                y_break_range=(100.0, 800.0),
            )
            with self.assertRaises(ValueError) as ctx:
                render_bridge_figure(spec)
            self.assertIn("overlay_baselines", str(ctx.exception))
            self.assertIn("y_break_range", str(ctx.exception))

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
