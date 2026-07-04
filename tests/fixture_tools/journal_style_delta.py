from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Mapping, Sequence

from tests.fixture_tools.journal_style_delta_validation import (
    PUBLIC_TRACKS,
    JsonObject,
    JsonValue,
    JournalStyleDeltaError,
    check_counts,
    diagnostic_delta,
    entry_for_track,
    json_object,
    matrix_tracks,
    named_delta,
    notable_checks,
    read_json_object,
    require_object,
    require_text,
    token_delta,
    track_data,
    track_tokens,
    validate_style_delta_report,
)

SUMMARY_ARTIFACT_PATH_KEYS: Final = ("copied_output_path", "output_path", "copied_manifest_path", "manifest_path")


@dataclass(frozen=True, slots=True)
class StyleDeltaRequest:
    matrix_path: Path
    fixture_id: str
    baseline_track: str = "nature"
    render_pack_summary_path: Path | None = None
    expected_dir: Path | None = None
    manifest_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DeltaContext:
    matrix: Mapping[str, JsonValue]
    baseline_track: str
    baseline_entry: Mapping[str, JsonValue]
    baseline_tokens: Mapping[str, JsonValue]
    render_pack_root: Path | None


def build_style_delta_report(request: StyleDeltaRequest) -> JsonObject:
    matrix = read_json_object(request.matrix_path)
    tracks = matrix_tracks(matrix)
    entries = _entries(request)
    baseline = entries.get(request.baseline_track)
    if baseline is None:
        raise JournalStyleDeltaError(f"missing baseline track: {request.baseline_track}")
    render_pack_root = request.render_pack_summary_path.resolve().parent if request.render_pack_summary_path is not None else None
    context = DeltaContext(matrix, request.baseline_track, baseline, track_tokens(matrix, request.baseline_track), render_pack_root)
    report: JsonObject = {
        "schema_version": "journal_style_delta_report/1",
        "report_kind": "style-delta",
        "generated_at": datetime.now(UTC).isoformat(),
        "comparison_scope": _scope(request, tracks),
        "baseline_track": request.baseline_track,
        "comparison_tracks": [track for track in tracks if track != request.baseline_track],
        "track_deltas": [_delta(track, entry_for_track(entries, track), context) for track in tracks],
        "claim_boundary": {
            "evidence_role": "comparison_evidence_only",
            "publishable_verdict": "not_a_publishable_verdict",
            "quality_threshold_policy": "no_arbitrary_pixel_difference_thresholds",
            "review_requirement": "Human review remains required; this report only compares encoded tokens and renderer diagnostics.",
        },
    }
    validate_style_delta_report(report, expected_tracks=tracks)
    return report


def render_markdown_summary(report: Mapping[str, JsonValue]) -> str:
    raw_deltas = report.get("track_deltas")
    if not isinstance(raw_deltas, list):
        raise JournalStyleDeltaError("track_deltas must be a list")
    lines = ["# Journal Style Delta Evidence", "", "This report compares encoded tokens and renderer diagnostics only; it is not a publishable verdict.", ""]
    for raw_delta in raw_deltas:
        if not isinstance(raw_delta, dict):
            raise JournalStyleDeltaError("track_delta must be an object")
        token = require_object(raw_delta, "token_delta")
        diagnostic = require_object(raw_delta, "diagnostic_delta")
        rationale = require_object(raw_delta, "visual_language_rationale")
        status = require_object(diagnostic, "status_delta")
        manual = require_object(diagnostic, "manual_review_delta")
        lines.extend([
            f"## {require_text(raw_delta, 'track')}",
            f"- token_floors: {_floors(token)}",
            f"- status: {status.get('candidate')} (reference: {status.get('reference')})",
            f"- manual_review_needed: {manual.get('candidate')} (reference: {manual.get('reference')})",
            f"- rationale: {require_text(rationale, 'summary')}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--fixture-id", default="basic_series")
    parser.add_argument("--baseline-track", default="nature")
    parser.add_argument("--render-pack-summary")
    parser.add_argument("--expected-dir")
    parser.add_argument("--manifest")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args(argv)
    request = StyleDeltaRequest(
        matrix_path=Path(args.matrix),
        fixture_id=args.fixture_id,
        baseline_track=args.baseline_track,
        render_pack_summary_path=Path(args.render_pack_summary) if args.render_pack_summary else None,
        expected_dir=Path(args.expected_dir) if args.expected_dir else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )
    report = build_style_delta_report(request)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown_summary(report), encoding="utf-8")
    print(json.dumps({"report_path": str(output_json.resolve()), "markdown_path": str(output_md.resolve())}))
    return 0


def _delta(track: str, entry: Mapping[str, JsonValue], context: DeltaContext) -> JsonObject:
    return {
        "track": track,
        "reference_track": context.baseline_track,
        "token_delta": token_delta(context.baseline_tokens, track_tokens(context.matrix, track)),
        "render_delta": {
            "output_dimensions": {"style_summary": named_delta(context.baseline_entry.get("style_summary"), entry.get("style_summary"))},
            "layout_density": {"layout_report": named_delta(check_counts(context.baseline_entry, "layout_report"), check_counts(entry, "layout_report"))},
            "legend_behavior": {"legend_checks": named_delta(notable_checks(context.baseline_entry, "layout_report"), notable_checks(entry, "layout_report"))},
            "rendered_output_metrics": _metrics(entry, context.render_pack_root),
            "artifact_paths": _paths(entry, context.render_pack_root),
        },
        "diagnostic_delta": {
            "status_delta": named_delta(context.baseline_entry.get("status"), entry.get("status")),
            "manual_review_delta": named_delta(context.baseline_entry.get("manual_review_needed"), entry.get("manual_review_needed")),
            "geometry_diagnostics": diagnostic_delta(context.baseline_entry, entry, "geometry_diagnostics"),
            "layout_report": diagnostic_delta(context.baseline_entry, entry, "layout_report"),
        },
        "visual_language_rationale": _rationale(context.matrix, track),
    }


def _entries(request: StyleDeltaRequest) -> dict[str, JsonObject]:
    if request.render_pack_summary_path is not None:
        summary = read_json_object(request.render_pack_summary_path)
        render_pack_root = request.render_pack_summary_path.resolve().parent
        raw_entries = summary.get("entries")
        if not isinstance(raw_entries, list):
            raise JournalStyleDeltaError("render pack summary entries must be a list")
        entries: dict[str, JsonObject] = {}
        for raw_entry in raw_entries:
            if isinstance(raw_entry, dict) and raw_entry.get("fixture_class") == request.fixture_id:
                entry = json_object(raw_entry)
                _merge_manifest(entry, render_pack_root)
                entries[require_text(entry, "track")] = entry
        return entries
    if request.expected_dir is None:
        raise JournalStyleDeltaError("render_pack_summary_path or expected_dir is required")
    return {
        track: _expected_entry(request.expected_dir / f"{track}_{request.fixture_id}.json", track)
        for track in PUBLIC_TRACKS
        if (request.expected_dir / f"{track}_{request.fixture_id}.json").is_file()
    }


def _expected_entry(path: Path, track: str) -> JsonObject:
    entry = read_json_object(path)
    entry.update({"status": "expected_summary", "manual_review_needed": False, "track": track})
    return entry


def _merge_manifest(entry: JsonObject, render_pack_root: Path) -> None:
    raw_path = entry.get("copied_manifest_path") or entry.get("manifest_path")
    if not isinstance(raw_path, str):
        return
    manifest_path = _resolve_summary_path(raw_path, render_pack_root, "manifest")
    if not manifest_path.is_file():
        return
    manifest = read_json_object(manifest_path)
    for key in ("style_summary", "geometry_diagnostics", "layout_report", "manual_review_needed"):
        if key in manifest:
            entry[key] = manifest[key]


def _scope(request: StyleDeltaRequest, tracks: Sequence[str]) -> JsonObject:
    dataset = request.fixture_id
    if request.manifest_path is not None and request.manifest_path.is_file():
        raw_classes = read_json_object(request.manifest_path).get("fixture_classes")
        if isinstance(raw_classes, list):
            dataset = next(
                (str(item.get("csv_path")) for item in raw_classes if isinstance(item, dict) and item.get("id") == request.fixture_id and item.get("csv_path")),
                dataset,
            )
    return {"fixture_id": request.fixture_id, "input_dataset": dataset, "renderer_surface": "figops.render_csv_graph", "output_format": "png", "tracks": list(tracks)}


def _rationale(matrix: Mapping[str, JsonValue], track: str) -> JsonObject:
    data = track_data(matrix, track)
    observed = data.get("observed_visual_language")
    if not isinstance(observed, list) or not observed or not isinstance(observed[0], dict):
        raise JournalStyleDeltaError(f"{track} missing visual_language_rationale")
    constraints = data.get("official_submission_constraints")
    evidence = [_basis(item) for item in observed if isinstance(item, dict)]
    if isinstance(constraints, list):
        evidence.extend(_source(item) for item in constraints if isinstance(item, dict))
    return {
        "summary": require_text(observed[0], "item"),
        "rationale_category": "observed_visual_language",
        "evidence_basis": [item for item in evidence if item],
        "unsupported_or_deferred": data.get("unsupported_or_deferred") if isinstance(data.get("unsupported_or_deferred"), list) else [],
        "claim_boundary": "publication-oriented comparison evidence, not a publishable verdict",
    }


def _metrics(entry: Mapping[str, JsonValue], render_pack_root: Path | None) -> JsonObject:
    raw_path = next((path for key in SUMMARY_ARTIFACT_PATH_KEYS[:2] if isinstance((path := entry.get(key)), str) and path), None)
    path = _resolve_summary_path(raw_path, render_pack_root, "output") if render_pack_root is not None and raw_path is not None else Path(raw_path) if raw_path is not None else None
    width, height = _png_size(path) if path is not None and path.is_file() else (None, None)
    return {
        "width_px": width or 1,
        "height_px": height or 1,
        "file_size_bytes": path.stat().st_size if path is not None and path.is_file() else 1,
        "pixel_threshold_policy": "not_used_as_quality_proof",
        "metric_source": "render_artifact" if path is not None and path.is_file() else "not_available_in_summary",
    }


def _png_size(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = struct.unpack(">II", header[16:24])
        return int(width), int(height)
    return None, None


def _paths(entry: Mapping[str, JsonValue], render_pack_root: Path | None) -> list[JsonValue]:
    return [
        str(_resolve_summary_path(raw_path, render_pack_root, key)) if render_pack_root is not None else raw_path
        for key in SUMMARY_ARTIFACT_PATH_KEYS
        if isinstance((raw_path := entry.get(key)), str) and raw_path
    ]


def _resolve_summary_path(raw_path: str, render_pack_root: Path, path_kind: str) -> Path:
    root = render_pack_root.resolve()
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise JournalStyleDeltaError(f"{path_kind} path is outside render pack root: {raw_path}")
    return resolved


def _floors(delta: Mapping[str, JsonValue]) -> str:
    parts: list[str] = []
    for group in ("font_floor_tokens", "line_floor_tokens", "dimension_tokens"):
        raw_group = delta.get(group)
        if isinstance(raw_group, dict):
            parts.extend(f"{key}={raw_delta.get('candidate')}" for key, raw_delta in raw_group.items() if isinstance(raw_delta, dict))
    return ", ".join(parts)


def _basis(item: Mapping[str, JsonValue]) -> str:
    text = item.get("item")
    basis = item.get("basis")
    return f"{text}: {basis}" if isinstance(text, str) and isinstance(basis, str) else ""


def _source(item: Mapping[str, JsonValue]) -> str:
    source = item.get("source_name")
    url = item.get("source_url")
    return f"{source} ({url})" if isinstance(source, str) and isinstance(url, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())
