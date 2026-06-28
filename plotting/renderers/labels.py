from __future__ import annotations

import math
from typing import Any

from plotting.utils import compress_sample_label

AVOID_OVERLAP_OFFSETS: tuple[tuple[float, float], ...] = (
    (8.0, 8.0),
    (-8.0, 8.0),
    (8.0, -8.0),
    (-8.0, -8.0),
    (0.0, 12.0),
    (12.0, 0.0),
)


def display_label(value: object, *, compress_labels: bool = True) -> str:
    text = str(value)
    if not compress_labels:
        return text
    return compress_sample_label(text)


def normalized_point_label_options_dict(raw_options: dict | None) -> dict[str, object]:
    if raw_options in (None, {}, []):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("point_label_options must be an object")
    allowed = {"offset", "fanout", "max_labels", "priority_column", "skip_column"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"point_label_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("offset") is not None:
        offset = raw_options["offset"]
        if not isinstance(offset, dict):
            raise ValueError("point_label_options.offset must be an object")
        try:
            dx = float(offset["dx"])
            dy = float(offset["dy"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("point_label_options.offset requires numeric dx and dy") from exc
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError("point_label_options.offset dx and dy must be finite")
        normalized["offset"] = (dx, dy)
    if raw_options.get("fanout") is not None:
        fanout = str(raw_options["fanout"]).strip().lower().replace("-", "_")
        if fanout not in {"none", "compass"}:
            raise ValueError("point_label_options.fanout must be 'none' or 'compass'")
        normalized["fanout"] = fanout
    if raw_options.get("max_labels") is not None:
        try:
            max_labels = int(raw_options["max_labels"])
        except (TypeError, ValueError) as exc:
            raise ValueError("point_label_options.max_labels must be an integer") from exc
        if max_labels < 1:
            raise ValueError("point_label_options.max_labels must be at least 1")
        normalized["max_labels"] = max_labels
    for key in ("priority_column", "skip_column"):
        if raw_options.get(key) is None or raw_options.get(key) == "":
            continue
        if not isinstance(raw_options[key], str):
            raise ValueError(f"point_label_options.{key} must be a string")
        column = raw_options[key].strip()
        if not column:
            raise ValueError(f"point_label_options.{key} must be a non-empty string when provided")
        normalized[key] = column
    return normalized


def annotate_points(
    ax: Any,
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    compress_labels: bool,
    point_label_options: dict | None = None,
    points: list[dict] | None = None,
) -> None:
    options = normalized_point_label_options_dict(point_label_options)
    candidates, skipped = point_label_candidates(xs, ys, labels, options=options, points=points)
    for display_index, item in enumerate(candidates):
        draw_point_label(ax, item, options=options, display_index=display_index, compress_labels=compress_labels)
    if skipped:
        record_point_label_skips(ax, skipped=skipped, total=len(labels), shown=len(candidates))


def point_label_candidates(
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    options: dict[str, object],
    points: list[dict] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    priority_column = str(options.get("priority_column") or "")
    skip_column = str(options.get("skip_column") or "")
    max_labels = options.get("max_labels")
    for index, (x, y, label) in enumerate(zip(xs, ys, labels)):
        if label:
            raw_row = {}
            if points is not None and index < len(points) and isinstance(points[index].get("raw"), dict):
                raw_row = points[index]["raw"]
            if skip_column and truthy_label_skip(raw_row.get(skip_column)):
                skipped.append({"index": index, "label": str(label), "reason": "skip_column"})
                continue
            priority = 0.0
            if priority_column:
                raw_priority = raw_row.get(priority_column, 0)
                try:
                    priority = float(raw_priority)
                except (TypeError, ValueError) as exc:
                    message = f"point_label_options.priority_column {priority_column!r} must be numeric"
                    raise ValueError(message) from exc
                if not math.isfinite(priority):
                    raise ValueError(f"point_label_options.priority_column {priority_column!r} must be finite")
            candidates.append({"index": index, "x": x, "y": y, "label": label, "priority": priority})
    if max_labels is not None:
        ranked = sorted(candidates, key=lambda item: (-float(item["priority"]), int(item["index"])))
        keep_indices = {int(item["index"]) for item in ranked[: int(max_labels)]}
        skipped.extend(
            {"index": int(item["index"]), "label": str(item["label"]), "reason": "max_labels"}
            for item in candidates
            if int(item["index"]) not in keep_indices
        )
        candidates = [item for item in candidates if int(item["index"]) in keep_indices]
    return candidates, skipped


def draw_point_label(
    ax: Any,
    item: dict[str, object],
    *,
    options: dict[str, object],
    display_index: int,
    compress_labels: bool,
) -> None:
    label = str(item["label"])
    if not label:
        return
    xytext = point_label_xytext(options, display_index)
    ax.annotate(
        display_label(label, compress_labels=compress_labels),
        (item["x"], item["y"]),
        textcoords="offset points",
        xytext=xytext,
        ha="center",
        va="bottom",
        zorder=5,
    )


def truthy_label_skip(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "skip", "hide"}


def point_label_xytext(options: dict[str, object], index: int) -> tuple[float, float]:
    offset = options.get("offset")
    if isinstance(offset, tuple):
        return offset
    if options.get("fanout") == "compass":
        return AVOID_OVERLAP_OFFSETS[index % len(AVOID_OVERLAP_OFFSETS)]
    return (0.0, 4.0)


def record_point_label_skips(
    ax: Any,
    *,
    skipped: list[dict[str, object]],
    total: int,
    shown: int,
) -> None:
    prior = getattr(ax, "_graph_hub_point_label_skips", None)
    if not isinstance(prior, dict):
        prior = {"total_labels": 0, "shown_labels": 0, "skipped_labels": 0, "reasons": {}, "examples": []}
    prior["total_labels"] = int(prior.get("total_labels", 0)) + int(total)
    prior["shown_labels"] = int(prior.get("shown_labels", 0)) + int(shown)
    prior["skipped_labels"] = int(prior.get("skipped_labels", 0)) + len(skipped)
    reasons = prior.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
    examples = prior.get("examples")
    if not isinstance(examples, list):
        examples = []
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        reasons[reason] = int(reasons.get(reason, 0)) + 1
        if len(examples) < 20:
            examples.append(
                {"index": int(item.get("index", -1)), "label": str(item.get("label") or ""), "reason": reason}
            )
    prior["reasons"] = reasons
    prior["examples"] = examples
    ax._graph_hub_point_label_skips = prior
