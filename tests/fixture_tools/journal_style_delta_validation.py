from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Mapping, Sequence

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

PUBLIC_TRACKS: Final = ("nature", "science", "acs", "rsc", "elsevier", "wiley", "cell")
TOKEN_GROUPS: Final[Mapping[str, tuple[str, ...]]] = {
    "dimension_tokens": ("figure_width_mm", "figure_height_mm", "figure_column_widths_mm", "max_figure_height_mm"),
    "font_floor_tokens": ("min_font_size_pt",),
    "line_floor_tokens": ("min_line_width_pt", "main_line_width", "timeseries_line_width", "error_line_width"),
    "marker_grammar_tokens": ("main_marker_size", "facet_marker_size", "main_marker_edge_width", "error_cap_size", "jitter_size", "violin_width"),
    "palette_tokens": ("default_colormap",),
    "legend_tokens": (),
}
RATIONALE_CATEGORIES: Final = (
    "official_submission_constraint",
    "encoded_figops_token",
    "observed_visual_language",
    "heuristic_publication_convention",
    "unsupported_or_deferred",
)
EXPECTED_TOKEN_FLOOR_PATHS: Final[Mapping[str, tuple[str, str]]] = {
    "min_font_size_pt": ("font_floor_tokens", "min_font_size_pt"),
    "min_line_width_pt": ("line_floor_tokens", "min_line_width_pt"),
    "max_figure_height_mm": ("dimension_tokens", "max_figure_height_mm"),
}


class JournalStyleDeltaError(RuntimeError):
    pass


def validate_style_delta_report(
    report: Mapping[str, JsonValue],
    *,
    expected_tracks: Sequence[str],
    expected_token_floors: Mapping[str, Mapping[str, JsonValue]] | None = None,
) -> None:
    if report.get("schema_version") != "journal_style_delta_report/1":
        raise JournalStyleDeltaError("schema_version must be journal_style_delta_report/1")
    raw_deltas = report.get("track_deltas")
    if not isinstance(raw_deltas, list):
        raise JournalStyleDeltaError("track_deltas must be a list")
    parsed: list[Mapping[str, JsonValue]] = []
    seen: set[str] = set()
    for index, raw_delta in enumerate(raw_deltas):
        if not isinstance(raw_delta, dict):
            raise JournalStyleDeltaError(f"track delta {index} must be an object")
        track = require_text(raw_delta, "track")
        seen.add(track)
        parsed.append(raw_delta)
    missing = [track for track in expected_tracks if track not in seen]
    if missing:
        raise JournalStyleDeltaError(f"missing track delta(s): {', '.join(missing)}")
    for raw_delta in parsed:
        track = require_text(raw_delta, "track")
        _require_rationale(raw_delta, track)
        _require_groups(raw_delta, track)
        if expected_token_floors is not None:
            _require_expected_token_floors(raw_delta, track, expected_token_floors)
    _require_unique_style_delta_signatures(parsed)


def read_json_object(path: Path) -> JsonObject:
    return json_object(json.loads(path.read_text(encoding="utf-8")))


def json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise JournalStyleDeltaError("JSON root must be an object")
    return value


def require_text(raw_object: Mapping[str, JsonValue], key: str) -> str:
    value = raw_object.get(key)
    if not isinstance(value, str) or not value:
        raise JournalStyleDeltaError(f"{key} must be a non-empty string")
    return value


def require_object(raw_object: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    value = raw_object.get(key)
    if not isinstance(value, dict):
        raise JournalStyleDeltaError(f"{key} must be an object")
    return value


def matrix_tracks(matrix: Mapping[str, JsonValue]) -> tuple[str, ...]:
    raw_tracks = matrix.get("public_tracks")
    if not isinstance(raw_tracks, dict):
        raise JournalStyleDeltaError("matrix public_tracks must be an object")
    missing = [track for track in PUBLIC_TRACKS if track not in raw_tracks]
    if missing:
        raise JournalStyleDeltaError(f"missing track in visual-language matrix: {', '.join(missing)}")
    return PUBLIC_TRACKS


def entry_for_track(entries: Mapping[str, JsonObject], track: str) -> JsonObject:
    entry = entries.get(track)
    if entry is None:
        raise JournalStyleDeltaError(f"missing track summary: {track}")
    return entry


def track_tokens(matrix: Mapping[str, JsonValue], track: str) -> Mapping[str, JsonValue]:
    tokens = track_data(matrix, track).get("encoded_figops_tokens")
    if not isinstance(tokens, dict):
        raise JournalStyleDeltaError(f"{track} encoded_figops_tokens must be an object")
    return tokens


def track_data(matrix: Mapping[str, JsonValue], track: str) -> Mapping[str, JsonValue]:
    raw_tracks = matrix.get("public_tracks")
    data = raw_tracks.get(track) if isinstance(raw_tracks, dict) else None
    if not isinstance(data, dict):
        raise JournalStyleDeltaError(f"missing track in visual-language matrix: {track}")
    return data


def token_delta(reference: Mapping[str, JsonValue], candidate: Mapping[str, JsonValue]) -> JsonObject:
    return {group: {key: named_delta(reference.get(key), candidate.get(key)) for key in keys} for group, keys in TOKEN_GROUPS.items()}


def diagnostic_delta(reference: Mapping[str, JsonValue], candidate: Mapping[str, JsonValue], key: str) -> JsonObject:
    ref = check_counts(reference, key)
    cand = check_counts(candidate, key)
    return {
        "passed_count_delta": int(cand["passed"]) - int(ref["passed"]),
        "failed_count_delta": int(cand["failed"]) - int(ref["failed"]),
        "unmeasured_count_delta": int(cand["unmeasured"]) - int(ref["unmeasured"]),
        "notable_checks": notable_checks(candidate, key),
    }


def check_counts(entry: Mapping[str, JsonValue], key: str) -> JsonObject:
    raw_report = entry.get(key)
    passed = failed = unmeasured = 0
    if isinstance(raw_report, dict):
        raw_checks = raw_report.get("checks")
        if isinstance(raw_checks, list):
            for raw_check in raw_checks:
                if isinstance(raw_check, dict):
                    passed += raw_check.get("passed") is True
                    failed += raw_check.get("passed") is False
                    unmeasured += raw_check.get("passed") is None
        else:
            passed += raw_report.get("passed") is True
            failed += raw_report.get("passed") is False
    return {"passed": passed, "failed": failed, "unmeasured": unmeasured}


def notable_checks(entry: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    raw_report = entry.get(key)
    names: list[JsonValue] = []
    if isinstance(raw_report, dict):
        raw_checks = raw_report.get("checks")
        if isinstance(raw_checks, list):
            names.extend(str(item.get("name", "unnamed_check")) for item in raw_checks if isinstance(item, dict) and item.get("passed") is not True)
        names.extend(f"{name}:{len(value)}" for name in ("render_errors", "warnings", "overlaps", "clipped") if isinstance((value := raw_report.get(name)), list) and value)
    return names


def named_delta(reference: JsonValue, candidate: JsonValue) -> JsonObject:
    if candidate == reference:
        delta: JsonValue = None
    elif isinstance(reference, int | float) and not isinstance(reference, bool) and isinstance(candidate, int | float) and not isinstance(candidate, bool):
        delta = round(float(candidate) - float(reference), 6)
    else:
        delta = "changed"
    return {"reference": reference, "candidate": candidate, "delta": delta, "interpretation": "same as reference" if delta is None else "differs from reference"}


def _require_groups(delta: Mapping[str, JsonValue], track: str) -> None:
    groups = (require_object(delta, "token_delta"), require_object(delta, "render_delta"), require_object(delta, "diagnostic_delta"))
    for key in TOKEN_GROUPS:
        if not isinstance(groups[0].get(key), dict):
            raise JournalStyleDeltaError(f"{track} missing token_delta group: {key}")
    for key in ("output_dimensions", "layout_density", "legend_behavior", "rendered_output_metrics", "artifact_paths"):
        if key not in groups[1]:
            raise JournalStyleDeltaError(f"{track} missing render_delta group: {key}")
    for key in ("status_delta", "manual_review_delta", "geometry_diagnostics", "layout_report"):
        if key not in groups[2]:
            raise JournalStyleDeltaError(f"{track} missing diagnostic_delta group: {key}")


def _require_rationale(delta: Mapping[str, JsonValue], track: str) -> None:
    rationale = require_object(delta, "visual_language_rationale")
    require_text(rationale, "summary")
    category = require_text(rationale, "rationale_category")
    if category not in RATIONALE_CATEGORIES:
        raise JournalStyleDeltaError(f"{track} unsupported rationale_category: {category}")
    evidence = rationale.get("evidence_basis")
    if not isinstance(evidence, list) or not any(isinstance(item, str) and item for item in evidence):
        raise JournalStyleDeltaError(f"{track} missing rationale evidence_basis")


def _require_unique_style_delta_signatures(deltas: Sequence[Mapping[str, JsonValue]]) -> None:
    signatures: dict[str, str] = {}
    for delta in deltas:
        track = require_text(delta, "track")
        signature = _style_delta_signature(delta)
        duplicate_track = signatures.get(signature)
        if duplicate_track is not None:
            raise JournalStyleDeltaError(f"{track} style-delta output duplicates {duplicate_track}")
        signatures[signature] = track


def _style_delta_signature(delta: Mapping[str, JsonValue]) -> str:
    token = require_object(delta, "token_delta")
    render = require_object(delta, "render_delta")
    diagnostic = require_object(delta, "diagnostic_delta")
    return json.dumps(
        {
            "token_delta": token,
            "render_delta": {
                "output_dimensions": render.get("output_dimensions"),
                "layout_density": render.get("layout_density"),
                "legend_behavior": render.get("legend_behavior"),
            },
            "diagnostic_delta": diagnostic,
        },
        sort_keys=True,
    )


def _require_expected_token_floors(
    delta: Mapping[str, JsonValue],
    track: str,
    expected_token_floors: Mapping[str, Mapping[str, JsonValue]],
) -> None:
    floors = expected_token_floors.get(track)
    if floors is None:
        raise JournalStyleDeltaError(f"{track} missing expected token floor data")
    token_delta = require_object(delta, "token_delta")
    for token_key, (group_key, delta_key) in EXPECTED_TOKEN_FLOOR_PATHS.items():
        group = require_object(token_delta, group_key)
        raw_delta = require_object(group, delta_key)
        if raw_delta.get("candidate") != floors.get(token_key):
            raise JournalStyleDeltaError(f"{track} stale expected token floor: {token_key}")
