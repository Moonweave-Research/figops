"""
[Graph_making_hub]/plotting/common_plots.py
============================================
High-level visualization utilities (Lean Version - No Seaborn Dependency)

- Matplotlib, Numpy, Pandas only
- Minimized external dependencies for portability
- Publication annotation helpers (p-value brackets, strip/violin plots)
"""

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_JITTER_HALF_WIDTH = 0.15
_DEFAULT_VIOLIN_KDE_POINTS = 100
_DEFAULT_VIOLIN_KDE_BW_METHOD = "scott"
_DEFAULT_VIOLIN_WIDTH = 0.5
_MIN_VIOLIN_KDE_POINTS = 16
_ALLOWED_VIOLIN_KDE_BW_METHODS = {"scott", "silverman"}


def _get_cycle_colors(n: int) -> list[str]:
    """Return *n* colors from the current rcParams prop_cycle."""
    cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["gray"])
    return [cycle[i % len(cycle)] for i in range(n)]


def _resolve_color(palette: dict | None, key: str, fallback_idx: int, cycle_colors: list[str]) -> str:
    if palette and key in palette:
        return palette[key]
    return cycle_colors[fallback_idx % len(cycle_colors)]


def _ensure_axes(ax: plt.Axes | None) -> tuple:
    if ax is None:
        fig, ax = plt.subplots()
    else:
        fig = ax.get_figure()
    return fig, ax


def _warn_small_n(n: int, group_name: str, threshold: int = 10) -> None:
    """Emit a warning when sample size is below *threshold* (Nature guidelines)."""
    if n < threshold:
        warnings.warn(
            f"Group '{group_name}' has n={n} (<{threshold}). "
            "Individual data points should be shown per Nature guidelines.",
            stacklevel=3,
        )


def _validate_violin_kde_points(kde_points: int) -> int:
    points = int(kde_points)
    if points < _MIN_VIOLIN_KDE_POINTS:
        raise ValueError(f"violin_kde_points must be >= {_MIN_VIOLIN_KDE_POINTS}")
    return points


def _validate_violin_kde_bw_method(bw_method):
    if bw_method is None or callable(bw_method):
        return bw_method
    if isinstance(bw_method, str):
        normalized = bw_method.strip().lower()
        if normalized not in _ALLOWED_VIOLIN_KDE_BW_METHODS:
            allowed = ", ".join(sorted(_ALLOWED_VIOLIN_KDE_BW_METHODS))
            raise ValueError(f"violin_kde_bw_method must be one of: {allowed}")
        return normalized
    bw_value = float(bw_method)
    if bw_value <= 0:
        raise ValueError("violin_kde_bw_method numeric value must be > 0")
    return bw_value


def _validate_violin_width(width: float) -> float:
    width_value = float(width)
    if width_value <= 0:
        raise ValueError("violin_width must be > 0")
    return width_value


# ---------------------------------------------------------------------------
# Existing helpers
# ---------------------------------------------------------------------------


def draw_pvalue_bracket(ax, x1, x2, y, text, h_factor=0.02, lw=0.8, color='black', fontsize=7):
    """Draw a significance bracket (p-value annotation) on an axes."""
    ylim = ax.get_ylim()
    if ax.get_yscale() == 'log':
        log_range = np.log10(ylim[1]) - np.log10(ylim[0])
        h = 10 ** (np.log10(y) + h_factor * log_range) - y
    else:
        h = h_factor * (ylim[1] - ylim[0])
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=lw, c=color)
    ax.text((x1 + x2) * 0.5, y + h * 1.2, text,
            ha='center', va='bottom', fontsize=fontsize)


def plot_grouped_summary(df, x_col, y_col, ax=None, palette=None, show_jitter=True, seed=42):
    """Bar + individual data point (jitter) overlay per category (Pure Matplotlib)."""
    rng = np.random.default_rng(seed)
    fig, ax = _ensure_axes(ax)

    categories = sorted(df[x_col].unique())
    x_pos = np.arange(len(categories))
    cycle_colors = _get_cycle_colors(len(categories))

    means = df.groupby(x_col)[y_col].mean()
    stds = df.groupby(x_col)[y_col].std()

    for i, cat in enumerate(categories):
        color = _resolve_color(palette, cat, i, cycle_colors)
        ax.bar(i, means[cat], color=color, edgecolor='black', lw=0.5, alpha=0.7)
        ax.errorbar(i, means[cat], yerr=stds[cat], fmt='none', ecolor='black', capsize=2, lw=0.8)

        if show_jitter:
            y_vals = df[df[x_col] == cat][y_col]
            x_jitter = rng.normal(i, 0.04, size=len(y_vals))
            ax.scatter(x_jitter, y_vals, s=8, fc='white', ec=color, lw=0.5, alpha=0.6, zorder=3)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(categories)
    return fig, ax


def plot_correlation_matrix(df, columns, method='pearson', title=None):
    """Correlation matrix heatmap (Pure Matplotlib)."""
    corr = df[columns].corr(method=method).values
    n = len(columns)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(columns, rotation=45, ha='right')
    ax.set_yticklabels(columns)

    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center",
                    color="white" if abs(corr[i, j]) > 0.5 else "black", fontsize=8)

    fig.colorbar(im, ax=ax, shrink=0.8)
    if title:
        ax.set_title(title)
    return fig, ax


# ---------------------------------------------------------------------------
# Statistical visualization (Nature-compliant)
# ---------------------------------------------------------------------------


def plot_strip_with_mean(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    ax: plt.Axes | None = None,
    palette: dict | None = None,
    show_mean: bool = True,
    show_median: bool = False,
    error_type: str = "sd",
    seed: int = 42,
) -> tuple:
    """Individual data points (jitter) + mean/median markers + error bars.

    Designed for materials science experiments with small n (3-5 replicates).
    Satisfies the Nature requirement: 'when n<10, show individual data points'.

    Args:
        error_type: 'sd' (standard deviation), 'sem' (standard error),
                    or 'ci95' (95% confidence interval).
    """
    rng = np.random.default_rng(seed)
    fig, ax = _ensure_axes(ax)

    categories = sorted(df[x_col].unique())
    x_pos = np.arange(len(categories))
    cycle_colors = _get_cycle_colors(len(categories))

    for i, cat in enumerate(categories):
        color = _resolve_color(palette, cat, i, cycle_colors)
        vals = df[df[x_col] == cat][y_col].dropna()
        n = len(vals)
        _warn_small_n(n, str(cat))

        x_jitter = rng.uniform(i - _JITTER_HALF_WIDTH, i + _JITTER_HALF_WIDTH, size=n)
        ax.scatter(x_jitter, vals, s=18, fc=color, ec="black", lw=0.4, alpha=0.7, zorder=3)

        if show_mean and n > 0:
            mean_val = vals.mean()
            if error_type == "sem":
                err = vals.std() / np.sqrt(n) if n > 1 else 0.0
            elif error_type == "ci95":
                err = 1.96 * vals.std() / np.sqrt(n) if n > 1 else 0.0
            else:  # sd
                err = vals.std() if n > 1 else 0.0
            ax.errorbar(i, mean_val, yerr=err, fmt="_", color="black",
                        markersize=12, markeredgewidth=1.5, capsize=4, lw=1.0, zorder=4)

        if show_median and n > 0:
            ax.plot(i, vals.median(), marker="D", color="black", markersize=4, zorder=5)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(categories)
    return fig, ax


def plot_box_with_points(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    ax: plt.Axes | None = None,
    palette: dict | None = None,
    seed: int = 42,
) -> tuple:
    """Box plot with individual data points overlaid for small-n transparency."""
    rng = np.random.default_rng(seed)
    fig, ax = _ensure_axes(ax)

    categories = sorted(df[x_col].unique())
    dataset = [df[df[x_col] == cat][y_col].dropna().values for cat in categories]
    positions = list(range(len(categories)))
    cycle_colors = _get_cycle_colors(len(categories))

    box = ax.boxplot(
        dataset,
        positions=positions,
        widths=0.5,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.0},
        whiskerprops={"color": "black", "linewidth": 0.8},
        capprops={"color": "black", "linewidth": 0.8},
    )
    for i, patch in enumerate(box["boxes"]):
        color = _resolve_color(palette, categories[i], i, cycle_colors)
        patch.set_facecolor(color)
        patch.set_edgecolor("black")
        patch.set_linewidth(0.6)
        patch.set_alpha(0.35)

    for i, (cat, vals) in enumerate(zip(categories, dataset)):
        _warn_small_n(len(vals), str(cat))
        color = _resolve_color(palette, cat, i, cycle_colors)
        x_jitter = rng.uniform(i - _JITTER_HALF_WIDTH, i + _JITTER_HALF_WIDTH, size=len(vals))
        ax.scatter(x_jitter, vals, s=18, fc=color, ec="black", lw=0.4, alpha=0.7, zorder=3)

    ax.set_xticks(positions)
    ax.set_xticklabels(categories)
    return fig, ax


def plot_violin_with_points(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    ax: plt.Axes | None = None,
    palette: dict | None = None,
    min_n: int = 10,
    kde_points: int = _DEFAULT_VIOLIN_KDE_POINTS,
    kde_bw_method=_DEFAULT_VIOLIN_KDE_BW_METHOD,
    violin_width: float = _DEFAULT_VIOLIN_WIDTH,
    seed: int = 42,
) -> tuple:
    """Violin plot with jitter overlay. Falls back to strip plot when n < min_n.

    Kernel density estimation is unreliable for very small samples, so this
    function automatically delegates to ``plot_strip_with_mean`` when any
    group has fewer than *min_n* observations.
    """
    categories = sorted(df[x_col].unique())
    group_sizes = {cat: len(df[df[x_col] == cat][y_col].dropna()) for cat in categories}

    if any(n < min_n for n in group_sizes.values()):
        small_groups = [f"{cat}(n={n})" for cat, n in group_sizes.items() if n < min_n]
        warnings.warn(
            f"Groups {', '.join(small_groups)} have n < {min_n}; "
            "falling back to strip plot (violin unreliable for small n).",
            stacklevel=2,
        )
        return plot_strip_with_mean(df, x_col, y_col, ax=ax, palette=palette, seed=seed)

    rng = np.random.default_rng(seed)
    fig, ax = _ensure_axes(ax)
    cycle_colors = _get_cycle_colors(len(categories))

    dataset = [df[df[x_col] == cat][y_col].dropna().values for cat in categories]
    positions = list(range(len(categories)))

    parts = ax.violinplot(
        dataset,
        positions=positions,
        widths=_validate_violin_width(violin_width),
        showmeans=False,
        showextrema=False,
        points=_validate_violin_kde_points(kde_points),
        bw_method=_validate_violin_kde_bw_method(kde_bw_method),
    )
    for i, body in enumerate(parts["bodies"]):
        color = _resolve_color(palette, categories[i], i, cycle_colors)
        body.set_facecolor(color)
        body.set_edgecolor("black")
        body.set_linewidth(0.5)
        body.set_alpha(0.5)

    for i, (cat, vals) in enumerate(zip(categories, dataset)):
        x_jitter = rng.uniform(i - _JITTER_HALF_WIDTH, i + _JITTER_HALF_WIDTH, size=len(vals))
        color = _resolve_color(palette, cat, i, cycle_colors)
        ax.scatter(x_jitter, vals, s=10, fc=color, ec="black", lw=0.3, alpha=0.6, zorder=3)

    ax.set_xticks(positions)
    ax.set_xticklabels(categories)
    return fig, ax
