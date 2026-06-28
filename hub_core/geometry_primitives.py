"""Low-level pixel-space geometry primitives for render diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.transforms import Bbox

GEOM_EPS_PX = 1.0


def _extent(artist: Any, renderer: Any) -> Bbox | None:
    try:
        bb = artist.get_window_extent(renderer)
    except (RuntimeError, ValueError):
        return None
    if bb is None or not np.all(np.isfinite(bb.get_points())):
        return None
    return bb


def _inter_area(box_a: Bbox, box_b: Bbox) -> float:
    inter = Bbox.intersection(box_a, box_b)
    if inter is None or inter.width <= 0 or inter.height <= 0:
        return 0.0
    area = inter.width * inter.height
    if area <= GEOM_EPS_PX**2:
        return 0.0
    return float(area)


def _boxes_overlap(box_a: Bbox, box_b: Bbox) -> bool:
    return _inter_area(box_a, box_b) > 0.0


def _box_area(box: Bbox) -> float:
    return float(abs(box.width) * abs(box.height))


def _overlap_fraction(box_a: Bbox, box_b: Bbox) -> float:
    denom = min(_box_area(box_a), _box_area(box_b))
    if denom <= 0:
        return 0.0
    return float(_inter_area(box_a, box_b) / denom)


def _circle_overlap_fraction(
    center_a: tuple[float, float],
    radius_a: float,
    center_b: tuple[float, float],
    radius_b: float,
) -> float:
    if radius_a <= 0 or radius_b <= 0:
        return 0.0
    distance = float(np.hypot(center_a[0] - center_b[0], center_a[1] - center_b[1]))
    if distance >= radius_a + radius_b:
        return 0.0
    smaller_area = np.pi * min(radius_a, radius_b) ** 2
    if smaller_area <= 0:
        return 0.0
    if distance <= abs(radius_a - radius_b):
        return 1.0
    term_a = radius_a**2 * np.arccos((distance**2 + radius_a**2 - radius_b**2) / (2 * distance * radius_a))
    term_b = radius_b**2 * np.arccos((distance**2 + radius_b**2 - radius_a**2) / (2 * distance * radius_b))
    term_c = 0.5 * np.sqrt(
        max(0.0, (-distance + radius_a + radius_b) * (distance + radius_a - radius_b))
        * max(0.0, (distance - radius_a + radius_b) * (distance + radius_a + radius_b))
    )
    return float((term_a + term_b - term_c) / smaller_area)


def _overlap_severity(value: float) -> str:
    if value >= 0.50:
        return "high"
    if value >= 0.20:
        return "medium"
    if value > 0:
        return "low"
    return "none"
