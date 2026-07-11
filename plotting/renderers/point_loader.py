"""CSV point loading and normalization for bridge-renderer specifications."""

from __future__ import annotations

import csv
import math
import warnings
from pathlib import Path
from typing import Any

from plotting.renderers.labels import normalized_point_label_options_dict


def normalized_point_label_options(spec: Any) -> dict[str, object]:
    return normalized_point_label_options_dict(spec.point_label_options)


def load_points(csv_path: Path, spec: Any) -> list[dict]:
    points: list[dict] = []
    skipped = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        required = [spec.x_column, spec.y_column]
        secondary_y = spec.secondary_y or {}
        secondary_y_column = str(secondary_y.get("column") or "").strip()
        if secondary_y_column:
            required.append(secondary_y_column)
        for col_attr in ("label_column", "series_column", "yerr_column", "yerr_minus_column", "facet_column"):
            col = getattr(spec, col_attr)
            if col:
                required.append(col)
        point_label_options = normalized_point_label_options(spec)
        for option_key in ("priority_column", "skip_column"):
            col = point_label_options.get(option_key)
            if col:
                required.append(str(col))
        for region in spec.fill_between:
            for key in ("x_column", "y1_column", "y2_column"):
                col = region.get(key)
                if col:
                    required.append(str(col))
        if spec.plot_type == "heatmap" and spec.z_column:
            required.append(spec.z_column)
        missing = [column for column in required if column not in headers]
        if missing:
            raise ValueError(
                f"CSV {csv_path.name} is missing column(s): {', '.join(missing)}. Available: {', '.join(headers)}"
            )
        for row in reader:
            try:
                y_val = float(row[spec.y_column])
                secondary_y_val = float(row[secondary_y_column]) if secondary_y_column else None
                yerr_val = float(row[spec.yerr_column]) if spec.yerr_column else None
                yerr_minus_val = float(row[spec.yerr_minus_column]) if spec.yerr_minus_column else None
                z_val = float(row[spec.z_column]) if spec.z_column else None
            except (ValueError, TypeError):
                skipped += 1
                continue
            if (
                not math.isfinite(y_val)
                or (secondary_y_val is not None and not math.isfinite(secondary_y_val))
                or (yerr_val is not None and not math.isfinite(yerr_val))
            ):
                skipped += 1
                continue
            if yerr_minus_val is not None and not math.isfinite(yerr_minus_val):
                skipped += 1
                continue
            if z_val is not None and not math.isfinite(z_val):
                skipped += 1
                continue
            points.append(
                {
                    "x": parse_x_value(row[spec.x_column]),
                    "y": y_val,
                    "secondary_y": secondary_y_val,
                    "z": z_val,
                    "label": row[spec.label_column] if spec.label_column else "",
                    "series": row[spec.series_column] if spec.series_column else "",
                    "yerr": yerr_val,
                    "yerr_minus": yerr_minus_val,
                    "facet": row[spec.facet_column] if spec.facet_column else "",
                    "raw": dict(row),
                }
            )
    if skipped:
        warnings.warn(
            f"bridge_renderer: skipped {skipped} row(s) with NaN/inf in {csv_path.name}",
            stacklevel=2,
        )
    if not points:
        raise ValueError(f"CSV {csv_path.name} contains no valid data rows")
    return points


def parse_x_value(value: object) -> float | str:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return float(text)
    except ValueError:
        return text
