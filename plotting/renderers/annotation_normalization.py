from __future__ import annotations

import math
import re

from plotting.renderers.labels import AVOID_OVERLAP_OFFSETS

CALLOUT_OFFSET_PRESETS: dict[str, tuple[float, float]] = {
    "above": (0.0, 10.0),
    "below": (0.0, -10.0),
    "left": (-10.0, 0.0),
    "right": (10.0, 0.0),
    "upper_left": (-8.0, 8.0),
    "upper_right": (8.0, 8.0),
    "lower_left": (-8.0, -8.0),
    "lower_right": (8.0, -8.0),
}
_ANNOTATION_P_CLAIM_RE = re.compile(
    r"^p(?:<=|<|=)[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$",
    re.IGNORECASE,
)


def _annotation_text(annotation: dict[str, object]) -> str:
    raw = str(annotation.get("text") or "")
    return raw if annotation.get("annotation_kind") == "literal" else raw.strip()


def _validate_annotation_claim(
    annotation: dict[str, object],
    index: int,
    evidence_by_id: dict[str, dict],
) -> None:
    text = _annotation_text(annotation)
    if not text:
        return
    compact = "".join(text.split()).replace("≤", "<=").replace("＜", "<").replace("＝", "=")
    recognized = bool(_ANNOTATION_P_CLAIM_RE.fullmatch(compact) or (compact and set(compact) == {"*"}))
    kind = str(annotation.get("annotation_kind") or "auto")
    if kind == "literal":
        return
    if not recognized and kind != "statistical_claim":
        return
    evidence_id = str(annotation.get("calculation_evidence_id") or "")
    evidence = evidence_by_id.get(evidence_id)
    if evidence is None:
        raise ValueError(f"annotations[{index}] statistical claim requires trusted, preverified calculation evidence")
    assertion = evidence.get("assertion") if isinstance(evidence.get("assertion"), dict) else {}
    if text != assertion.get("display_label"):
        raise ValueError(f"annotations[{index}].text does not match calculation evidence")
    if annotation.get("analysis_artifact_sha256") != evidence.get("analysis_artifact_sha256"):
        raise ValueError(f"annotations[{index}].analysis_artifact_sha256 does not match calculation evidence")
    if annotation.get("test_metadata") != evidence.get("test_metadata"):
        raise ValueError(f"annotations[{index}].test_metadata does not match calculation evidence")


def reject_non_point_callout_fields(annotation: dict[str, object], index: int) -> None:
    unsupported = [
        key
        for key in ("xytext_offset", "placement_preset", "avoid_overlap")
        if key in annotation and annotation.get(key) is not None
    ]
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"annotations[{index}] {joined} only apply to point annotations")


def normalized_callout_offset(annotation: dict[str, object], index: int) -> tuple[float, float] | None:
    raw_offset = annotation.get("xytext_offset")
    if raw_offset is not None:
        if not isinstance(raw_offset, dict):
            raise ValueError(f"annotations[{index}].xytext_offset must be an object")
        try:
            dx = float(raw_offset["dx"])
            dy = float(raw_offset["dy"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"annotations[{index}].xytext_offset requires numeric dx and dy") from exc
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError(f"annotations[{index}].xytext_offset dx and dy must be finite")
        return (dx, dy)
    preset = str(annotation.get("placement_preset") or "").strip().lower().replace("-", "_")
    if preset:
        if preset not in CALLOUT_OFFSET_PRESETS:
            allowed = ", ".join(sorted(CALLOUT_OFFSET_PRESETS))
            raise ValueError(f"annotations[{index}].placement_preset must be one of: {allowed}")
        return CALLOUT_OFFSET_PRESETS[preset]
    raw_avoid_overlap = annotation.get("avoid_overlap", False)
    if not isinstance(raw_avoid_overlap, bool):
        raise ValueError(f"annotations[{index}].avoid_overlap must be a boolean")
    if raw_avoid_overlap:
        return AVOID_OVERLAP_OFFSETS[index % len(AVOID_OVERLAP_OFFSETS)]
    return None


def normalized_span_annotation(
    annotation: dict[str, object],
    index: int,
    *,
    field: str,
    bounds: tuple[str, str],
) -> dict[str, object]:
    span = annotation[field]
    if not isinstance(span, dict):
        raise ValueError(f"annotations[{index}].{field} must be an object")
    lower_key, upper_key = bounds
    try:
        lower = float(span[lower_key])
        upper = float(span[upper_key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"annotations[{index}].{field} requires numeric {lower_key} and {upper_key}") from exc
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise ValueError(f"annotations[{index}].{field} bounds must be finite")
    try:
        alpha = float(annotation.get("alpha", 0.12))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"annotations[{index}].alpha must be numeric") from exc
    return {
        "kind": field,
        lower_key: lower,
        upper_key: upper,
        "text": _annotation_text(annotation),
        "color": str(annotation.get("color") or "black"),
        "alpha": alpha,
    }


def normalized_annotations(
    annotations: object,
    *,
    calculation_evidence: object = (),
) -> tuple[dict[str, object], ...]:
    if annotations in (None, (), []):
        return ()
    if not isinstance(annotations, (list, tuple)):
        raise ValueError("annotations must be an array of objects")
    if not isinstance(calculation_evidence, (list, tuple)):
        raise ValueError("calculation_evidence must be an array")
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in calculation_evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    normalized: list[dict[str, object]] = []
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            raise ValueError(f"annotations[{index}] must be an object")
        _validate_annotation_claim(annotation, index, evidence_by_id)
        region = annotation.get("region")
        if region is not None:
            reject_non_point_callout_fields(annotation, index)
            if not isinstance(region, dict):
                raise ValueError(f"annotations[{index}].region must be an object")
            try:
                xmin = float(region["xmin"])
                xmax = float(region["xmax"])
                ymin = float(region["ymin"])
                ymax = float(region["ymax"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].region requires numeric xmin, xmax, ymin, ymax") from exc
            if not all(math.isfinite(value) for value in (xmin, xmax, ymin, ymax)):
                raise ValueError(f"annotations[{index}].region bounds must be finite")
            try:
                alpha = float(annotation.get("alpha", 0.12))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].alpha must be numeric") from exc
            normalized.append(
                {
                    "kind": "region",
                    "xmin": xmin,
                    "xmax": xmax,
                    "ymin": ymin,
                    "ymax": ymax,
                    "text": _annotation_text(annotation),
                    "color": str(annotation.get("color") or "black"),
                    "alpha": alpha,
                }
            )
            continue
        if annotation.get("hspan") is not None:
            reject_non_point_callout_fields(annotation, index)
            normalized.append(normalized_span_annotation(annotation, index, field="hspan", bounds=("ymin", "ymax")))
            continue
        if annotation.get("vspan") is not None:
            reject_non_point_callout_fields(annotation, index)
            normalized.append(normalized_span_annotation(annotation, index, field="vspan", bounds=("xmin", "xmax")))
            continue
        missing = [key for key in ("x", "y") if key not in annotation]
        if missing:
            raise ValueError(f"annotations[{index}] missing required field(s): {', '.join(missing)}")
        try:
            x = float(annotation["x"])
            y = float(annotation["y"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"annotations[{index}] x and y must be numeric") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"annotations[{index}] x and y must be finite")
        text = _annotation_text(annotation)
        arrow_to = annotation.get("arrow_to")
        if not text and arrow_to is None:
            raise ValueError(f"annotations[{index}] text must be non-empty unless arrow_to is provided")
        normalized_arrow = None
        if arrow_to is not None:
            if not isinstance(arrow_to, dict):
                raise ValueError(f"annotations[{index}].arrow_to must be an object")
            try:
                arrow_x = float(arrow_to["x"])
                arrow_y = float(arrow_to["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].arrow_to requires numeric x and y") from exc
            if not math.isfinite(arrow_x) or not math.isfinite(arrow_y):
                raise ValueError(f"annotations[{index}].arrow_to x and y must be finite")
            normalized_arrow = {"x": arrow_x, "y": arrow_y}
        arrowstyle = str(annotation.get("arrowstyle") or "->").strip() or "->"
        connectionstyle = str(annotation.get("connectionstyle") or "").strip()
        item = {
            "kind": "point",
            "x": x,
            "y": y,
            "text": text,
            "arrow_to": normalized_arrow,
            "color": str(annotation.get("color") or "black"),
            "arrowstyle": arrowstyle,
        }
        callout_offset = normalized_callout_offset(annotation, index)
        if callout_offset is not None:
            item["xytext_offset"] = callout_offset
        if connectionstyle:
            item["connectionstyle"] = connectionstyle
        normalized.append(item)
    return tuple(normalized)
