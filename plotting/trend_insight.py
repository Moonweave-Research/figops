"""
[Graph_making_hub]/plotting/trend_insight.py
=============================================
피크/골/변곡점 자동 감지 및 matplotlib Axes 주석 렌더링 모듈.
"""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from scipy.signal import find_peaks


def _detect_peaks(y: np.ndarray, **kwargs) -> np.ndarray:
    indices, _ = find_peaks(y, **kwargs)
    return indices


def _detect_valleys(y: np.ndarray, **kwargs) -> np.ndarray:
    indices, _ = find_peaks(-y, **kwargs)
    return indices


def _detect_inflections(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    d2 = np.gradient(np.gradient(y, x), x)
    # x에 중복값이 있으면 gradient가 nan/inf를 반환 → 오탐 방지를 위해 제거
    d2 = np.where(np.isfinite(d2), d2, 0.0)
    sign_changes = np.where(np.diff(np.sign(d2)))[0]
    return sign_changes


def annotate_trends(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    *,
    peaks: bool = True,
    valleys: bool = True,
    inflections: bool = False,
    style: str = "callout",
    peak_kwargs: dict | None = None,
    valley_kwargs: dict | None = None,
) -> list:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    peak_find_kwargs = peak_kwargs or {}
    valley_find_kwargs = valley_kwargs or {}

    annotations: list = []

    if peaks:
        peak_indices = _detect_peaks(y, **peak_find_kwargs)
        for idx in peak_indices:
            x_val = x[idx]
            y_val = y[idx]
            label = f"({x_val:.2g}, {y_val:.2g})"
            if style == "callout":
                ann = ax.annotate(
                    label,
                    xy=(x_val, y_val),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    arrowprops=dict(arrowstyle="->", lw=0.8),
                )
            else:
                (ann,) = ax.plot(x_val, y_val, marker="^", markersize=5, linestyle="none")
            annotations.append(ann)

    if valleys:
        valley_indices = _detect_valleys(y, **valley_find_kwargs)
        for idx in valley_indices:
            x_val = x[idx]
            y_val = y[idx]
            label = f"({x_val:.2g}, {y_val:.2g})"
            if style == "callout":
                ann = ax.annotate(
                    label,
                    xy=(x_val, y_val),
                    xytext=(0, -8),
                    textcoords="offset points",
                    ha="center",
                    va="top",
                    fontsize=7,
                    arrowprops=dict(arrowstyle="->", lw=0.8),
                )
            else:
                (ann,) = ax.plot(x_val, y_val, marker="v", markersize=5, linestyle="none")
            annotations.append(ann)

    if inflections:
        inflection_indices = _detect_inflections(x, y)
        for idx in inflection_indices:
            x_val = x[idx]
            y_val = y[idx]
            label = f"({x_val:.2g}, {y_val:.2g})"
            if style == "callout":
                ann = ax.annotate(
                    label,
                    xy=(x_val, y_val),
                    xytext=(0, 8),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    arrowprops=dict(arrowstyle="->", lw=0.8),
                )
            else:
                (ann,) = ax.plot(x_val, y_val, marker="o", markersize=4, linestyle="none")
            annotations.append(ann)

    return annotations
