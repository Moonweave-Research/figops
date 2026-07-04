from __future__ import annotations

import argparse
import html
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Mapping, Sequence

HUB_ROOT = Path(__file__).resolve().parents[2]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

from tests.fixture_tools.journal_style_delta import StyleDeltaRequest, build_style_delta_report
from tests.fixture_tools.journal_style_delta_validation import JsonObject, JsonValue, check_counts

FIXTURE_ROOT = HUB_ROOT / "tests" / "fixtures" / "journal_tracks"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
MATRIX_PATH = HUB_ROOT / "docs" / "specs" / "2026-07-04-journal-visual-language-matrix.json"


def _read_json(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return raw


def _case_entries(manifest: Mapping[str, JsonValue], requested_case: str) -> list[JsonObject]:
    entries = manifest["fixture_classes"]
    if not isinstance(entries, list):
        raise SystemExit("manifest fixture_classes must be a list")
    if requested_case == "all":
        return [entry for entry in entries if isinstance(entry, dict)]
    selected = [entry for entry in entries if isinstance(entry, dict) and entry["id"] == requested_case]
    if not selected:
        raise SystemExit(f"unknown fixture case: {requested_case}")
    return selected


def _copy_artifact(source: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination.resolve())


def _render_fixture(server, fixture: Mapping[str, JsonValue], track: str, output_dir: Path) -> JsonObject:
    arguments = dict(fixture["render_arguments"])
    fixture_id = str(fixture["id"])
    arguments.update(
        {
            "data_path": str((FIXTURE_ROOT / fixture["csv_path"]).resolve()),
            "target_format": track,
            "profile": "baseline",
            "output_format": "png",
            "overwrite": True,
            "job_id": f"journal-{fixture_id}-{track}",
        }
    )
    response = server.call_tool("figops.render_csv_graph", arguments)
    result = response["structuredContent"]
    stem = f"{fixture_id}_{track}"
    output_path = Path(result["output_path"])
    manifest_path = Path(result["manifest_path"])
    result["fixture_class"] = fixture_id
    result["track"] = track
    result["copied_output_path"] = _copy_artifact(str(output_path), output_dir / f"{stem}{output_path.suffix}")
    result["copied_manifest_path"] = _copy_artifact(str(manifest_path), output_dir / f"{stem}_manifest.json")
    return result


def _write_contact_sheet(summary: Mapping[str, JsonValue], style_reports: Mapping[str, JsonObject], contact_sheet: Path) -> None:
    cards = []
    base = contact_sheet.parent.resolve()
    raw_entries = summary["entries"]
    if not isinstance(raw_entries, list):
        raise SystemExit("summary entries must be a list")
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise SystemExit("summary entry must be an object")
        image_path = Path(entry["copied_output_path"]).resolve()
        relative = Path(os.path.relpath(image_path, start=base)).as_posix()
        fixture_class = str(entry["fixture_class"])
        track = str(entry["track"])
        report = style_reports[fixture_class]
        caption = html.escape(
            " | ".join(
                (
                    f"fixture_class={fixture_class}",
                    f"track={track}",
                    f"status={entry['status']}",
                    f"manual_review_needed={entry['manual_review_needed']}",
                    _dimension_caption(report, track),
                    _diagnostic_caption(entry),
                )
            )
        )
        cards.append(f"<figure><img src=\"{relative}\" alt=\"{caption}\"><figcaption>{caption}</figcaption></figure>")
    markup = (
        "<!doctype html><meta charset=\"utf-8\"><title>Journal track fixtures</title>"
        "<style>body{font-family:sans-serif;margin:24px}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}"
        "figure{margin:0;border:1px solid #ddd;padding:8px}"
        "img{max-width:100%;height:auto;display:block}"
        "figcaption{font-size:12px;margin-top:6px}</style>"
        f"<main>{''.join(cards)}</main>"
    )
    contact_sheet.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet.write_text(markup, encoding="utf-8")


def _build_style_reports(summary_path: Path, fixture_ids: Sequence[str]) -> dict[str, JsonObject]:
    return {
        fixture_id: build_style_delta_report(
            StyleDeltaRequest(
                matrix_path=MATRIX_PATH,
                fixture_id=fixture_id,
                render_pack_summary_path=summary_path,
                manifest_path=MANIFEST_PATH,
            )
        )
        for fixture_id in fixture_ids
    }


def _style_delta_summary(style_reports: Mapping[str, JsonObject]) -> JsonObject:
    if len(style_reports) == 1:
        return next(iter(style_reports.values()))
    return {
        "schema_version": "journal_track_render_pack_style_delta_summary/1",
        "fixture_reports": list(style_reports.values()),
    }


def _dimension_caption(report: Mapping[str, JsonValue], track: str) -> str:
    raw_deltas = report.get("track_deltas")
    if not isinstance(raw_deltas, list):
        raise SystemExit("style delta track_deltas must be a list")
    for raw_delta in raw_deltas:
        if not isinstance(raw_delta, dict) or raw_delta.get("track") != track:
            continue
        raw_tokens = raw_delta.get("token_delta")
        raw_dimensions = raw_tokens.get("dimension_tokens") if isinstance(raw_tokens, dict) else None
        if not isinstance(raw_dimensions, dict):
            raise SystemExit(f"{track} missing dimension token deltas")
        parts = [
            f"{key}={value.get('candidate')} delta={value.get('delta')}"
            for key, value in raw_dimensions.items()
            if isinstance(value, dict)
        ]
        return f"dimension_tokens: {', '.join(parts)}"
    raise SystemExit(f"missing style delta for track: {track}")


def _diagnostic_caption(entry: Mapping[str, JsonValue]) -> str:
    geometry_counts = check_counts(entry, "geometry_diagnostics")
    layout_counts = check_counts(entry, "layout_report")
    unmeasured = int(geometry_counts["unmeasured"]) + int(layout_counts["unmeasured"])
    return f"warnings={_warning_count(entry)} unmeasured={unmeasured}"


def _warning_count(entry: Mapping[str, JsonValue]) -> int:
    count = _list_count(entry.get("warnings"))
    for key in ("geometry_diagnostics", "layout_report", "visual_preflight_status", "baseline_comparison"):
        raw_report = entry.get(key)
        if isinstance(raw_report, dict):
            count += _list_count(raw_report.get("warnings"))
    return count


def _list_count(value: JsonValue | None) -> int:
    return len(value) if isinstance(value, list) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="all")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--contact-sheet")
    args = parser.parse_args()

    manifest = _read_json(MANIFEST_PATH)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mcp_module = importlib.import_module("hub_core.mcp")
    server = mcp_module.GraphHubMCPServer(
        research_root=HUB_ROOT,
        runtime_root=output_dir / "_runtime",
        write_tools_enabled=True,
    )
    selected_fixtures = _case_entries(manifest, args.case)
    entries = [
        _render_fixture(server, fixture, track, output_dir)
        for fixture in selected_fixtures
        for track in manifest["public_tracks"]
    ]
    summary = {
        "schema_version": "journal_track_render_pack/1",
        "entries": entries,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    fixture_ids = [str(fixture["id"]) for fixture in selected_fixtures]
    style_reports = _build_style_reports(summary_path, fixture_ids)
    style_delta_summary_path = output_dir / "style_delta_summary.json"
    style_delta_summary_path.write_text(json.dumps(_style_delta_summary(style_reports), indent=2, sort_keys=True), encoding="utf-8")
    if args.contact_sheet:
        _write_contact_sheet(summary, style_reports, Path(args.contact_sheet).resolve())
    print(
        json.dumps(
            {
                "entries": len(entries),
                "summary_path": str(summary_path.resolve()),
                "style_delta_summary_path": str(style_delta_summary_path.resolve()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
