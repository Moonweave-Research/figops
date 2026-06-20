"""Unit tests for plotting/common_plots.py — statistical visualization helpers."""

import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from plotting.common_plots import (  # noqa: E402
    _warn_small_n,
    plot_strip_with_mean,
    plot_violin_with_points,
)


@pytest.fixture(autouse=True)
def _cleanup_plots():
    yield
    plt.close("all")


@pytest.fixture
def small_df():
    """n=3 per group -- typical materials science replicates."""
    return pd.DataFrame({
        "sample": ["A"] * 3 + ["B"] * 3,
        "value": [1.2, 1.5, 1.3, 2.1, 2.4, 2.2],
    })


@pytest.fixture
def large_df():
    """n=20 per group -- sufficient for violin."""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "sample": ["A"] * 20 + ["B"] * 20,
        "value": np.concatenate([rng.normal(1.3, 0.2, 20), rng.normal(2.2, 0.3, 20)]),
    })


class TestWarnSmallN:
    def test_fires_below_threshold(self):
        with pytest.warns(UserWarning, match=r"Group 'X' has n=3 \(<10\)"):
            _warn_small_n(3, "X")

    def test_silent_above_threshold(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _warn_small_n(15, "Y")


class TestPlotStripWithMean:
    def test_returns_fig_ax(self, small_df):
        fig, ax = plot_strip_with_mean(small_df, "sample", "value")
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)

    def test_shows_all_points(self, small_df):
        fig, ax = plot_strip_with_mean(small_df, "sample", "value")
        # PathCollections from scatter (not errorbar LineCollections)
        from matplotlib.collections import PathCollection
        scatter_points = sum(
            len(c.get_offsets()) for c in ax.collections if isinstance(c, PathCollection)
        )
        assert scatter_points == 6

    def test_error_types_run_without_error(self, small_df):
        for etype in ("sd", "sem", "ci95"):
            fig, ax = plot_strip_with_mean(small_df, "sample", "value", error_type=etype)
            assert fig is not None

    def test_accepts_external_ax(self, small_df):
        fig, ax = plt.subplots()
        returned_fig, returned_ax = plot_strip_with_mean(small_df, "sample", "value", ax=ax)
        assert returned_ax is ax


class TestPlotViolinWithPoints:
    def test_small_n_warns_and_falls_back(self, small_df):
        with pytest.warns(UserWarning, match="falling back to strip plot"):
            fig, ax = plot_violin_with_points(small_df, "sample", "value")
        assert isinstance(fig, plt.Figure)
        violin_bodies = [c for c in ax.collections
                         if "PolyCollection" in type(c).__name__]
        assert violin_bodies == []

    def test_large_n_creates_violin(self, large_df):
        fig, ax = plot_violin_with_points(large_df, "sample", "value")
        # matplotlib >= 3.9 uses FillBetweenPolyCollection for violin bodies
        violin_bodies = [c for c in ax.collections
                         if "PolyCollection" in type(c).__name__]
        assert len(violin_bodies) >= 2
