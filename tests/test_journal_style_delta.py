from __future__ import annotations

import copy
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.fixture_tools.journal_style_delta import StyleDeltaRequest, build_style_delta_report
from tests.fixture_tools.journal_style_delta_validation import (
    PUBLIC_TRACKS,
    RATIONALE_CATEGORIES,
    TOKEN_GROUPS,
    JsonValue,
    JournalStyleDeltaError,
    read_json_object,
    validate_style_delta_report,
)

HUB_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = HUB_ROOT / "tests" / "fixtures" / "journal_tracks"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
MATRIX_PATH = HUB_ROOT / "docs" / "specs" / "2026-07-04-journal-visual-language-matrix.json"


class _ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        for name, value in attrs:
            if name == "src" and value is not None:
                self.sources.append(value)
                return


def test_style_delta_report_builds_all_public_track_deltas() -> None:
    # Given: the committed visual-language matrix and expected render summaries.
    request = StyleDeltaRequest(
        matrix_path=MATRIX_PATH,
        fixture_id="basic_series",
        expected_dir=EXPECTED_ROOT,
        manifest_path=MANIFEST_PATH,
    )

    # When: the helper builds the style-delta report from real fixture inputs.
    report = build_style_delta_report(request)

    # Then: all public tracks and required contract groups are present.
    validate_style_delta_report(
        report,
        expected_tracks=PUBLIC_TRACKS,
        expected_token_floors=_expected_token_floors("basic_series"),
    )
    raw_deltas = report["track_deltas"]
    assert isinstance(raw_deltas, list)
    assert [delta["track"] for delta in raw_deltas if isinstance(delta, dict)] == list(PUBLIC_TRACKS)
    assert report["baseline_track"] == "nature"
    assert report["comparison_tracks"] == list(PUBLIC_TRACKS[1:])
    for raw_delta in raw_deltas:
        assert isinstance(raw_delta, dict)
        assert set(raw_delta["token_delta"]) == set(TOKEN_GROUPS)
        assert {"output_dimensions", "layout_density", "legend_behavior", "rendered_output_metrics", "artifact_paths"} <= set(raw_delta["render_delta"])
        assert {"status_delta", "manual_review_delta", "geometry_diagnostics", "layout_report"} <= set(raw_delta["diagnostic_delta"])
        rationale = raw_delta["visual_language_rationale"]
        assert isinstance(rationale, dict)
        assert rationale["rationale_category"] == "observed_visual_language"


def test_style_delta_report_rejects_missing_public_track() -> None:
    # Given: an otherwise valid style-delta report that omits one required public track.
    report = _basic_series_style_delta_report()
    omitted_track = PUBLIC_TRACKS[-1]
    raw_deltas = report["track_deltas"]
    assert isinstance(raw_deltas, list)
    report["track_deltas"] = [
        delta for delta in raw_deltas if isinstance(delta, dict) and delta.get("track") != omitted_track
    ]

    # When / Then: helper validation rejects the incomplete track set.
    with pytest.raises(JournalStyleDeltaError, match="missing track"):
        validate_style_delta_report(report, expected_tracks=PUBLIC_TRACKS)


def test_style_delta_report_rejects_missing_visual_language_rationale() -> None:
    # Given: a style-delta report where one track omits its rationale block.
    report = {
        "schema_version": "journal_style_delta_report/1",
        "track_deltas": [{"track": track, "visual_language_rationale": {"summary": track}} for track in PUBLIC_TRACKS],
    }
    del report["track_deltas"][0]["visual_language_rationale"]

    # When / Then: helper validation rejects the malformed track delta.
    with pytest.raises(JournalStyleDeltaError, match="visual_language_rationale"):
        validate_style_delta_report(report, expected_tracks=PUBLIC_TRACKS)


def test_style_delta_report_rejects_corrupted_rationale_category() -> None:
    # Given: a real style-delta report with one rationale category corrupted.
    report = _basic_series_style_delta_report()
    raw_deltas = report["track_deltas"]
    assert isinstance(raw_deltas, list)
    raw_delta = raw_deltas[1]
    assert isinstance(raw_delta, dict)
    rationale = raw_delta["visual_language_rationale"]
    assert isinstance(rationale, dict)
    rationale["rationale_category"] = "forced_visual_difference"

    # When / Then: helper validation rejects undocumented rationale categories.
    with pytest.raises(JournalStyleDeltaError, match="rationale_category"):
        validate_style_delta_report(
            report,
            expected_tracks=PUBLIC_TRACKS,
            expected_token_floors=_expected_token_floors("basic_series"),
        )


def test_style_delta_report_accepts_documented_rationale_categories() -> None:
    # Given: a real style-delta report and each documented rationale category.
    report = _basic_series_style_delta_report()
    raw_deltas = report["track_deltas"]
    assert isinstance(raw_deltas, list)
    raw_delta = raw_deltas[1]
    assert isinstance(raw_delta, dict)
    rationale = raw_delta["visual_language_rationale"]
    assert isinstance(rationale, dict)

    # When / Then: helper validation accepts known non-empty rationale categories.
    for category in RATIONALE_CATEGORIES:
        rationale["rationale_category"] = category
        validate_style_delta_report(
            report,
            expected_tracks=PUBLIC_TRACKS,
            expected_token_floors=_expected_token_floors("basic_series"),
        )


def test_style_delta_report_rejects_stale_expected_token_floor() -> None:
    # Given: a real style-delta report and a stale expected token floor.
    report = _basic_series_style_delta_report()
    stale_token_floors = copy.deepcopy(_expected_token_floors("basic_series"))
    stale_token_floors["science"]["min_font_size_pt"] = 6.0

    # When / Then: helper validation rejects the stale expected fixture token floor.
    with pytest.raises(JournalStyleDeltaError, match="expected token floor"):
        validate_style_delta_report(
            report,
            expected_tracks=PUBLIC_TRACKS,
            expected_token_floors=stale_token_floors,
        )


def test_style_delta_report_rejects_render_summary_manifest_path_escape(tmp_path: Path) -> None:
    # Given: a stale render-pack summary that points its copied manifest outside the pack root.
    pack_root = tmp_path / "render_pack"
    pack_root.mkdir()
    outside_manifest = tmp_path / "outside_manifest.json"
    outside_manifest.write_text(
        json.dumps({"style_summary": {"target_format": "nature"}}),
        encoding="utf-8",
    )
    summary_path = pack_root / "summary.json"
    _write_render_pack_summary(summary_path, "copied_manifest_path", str(outside_manifest))

    # When / Then: summary-provided manifest paths outside the pack root are rejected before read.
    with pytest.raises(JournalStyleDeltaError, match="outside render pack root"):
        build_style_delta_report(
            StyleDeltaRequest(
                matrix_path=MATRIX_PATH,
                fixture_id="path_escape",
                render_pack_summary_path=summary_path,
            )
        )


def test_style_delta_report_rejects_render_summary_output_path_escape(tmp_path: Path) -> None:
    # Given: a stale render-pack summary that points its copied output outside the pack root.
    pack_root = tmp_path / "render_pack"
    pack_root.mkdir()
    outside_output = tmp_path / "outside.png"
    outside_output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + b"\x00\x00\x00\x01\x00\x00\x00\x01")
    summary_path = pack_root / "summary.json"
    _write_render_pack_summary(summary_path, "copied_output_path", str(outside_output))

    # When / Then: summary-provided output paths outside the pack root are rejected before stat/open.
    with pytest.raises(JournalStyleDeltaError, match="outside render pack root"):
        build_style_delta_report(
            StyleDeltaRequest(
                matrix_path=MATRIX_PATH,
                fixture_id="path_escape",
                render_pack_summary_path=summary_path,
            )
        )


def test_render_pack_cli_writes_style_delta_summary_and_caption_contract(tmp_path: Path) -> None:
    # Given: the same-dataset fixture pack is rendered through the real MCP CLI surface.
    fixture_id = "same_dataset_user_dogfood"
    evidence_dir = tmp_path / "evidence"
    output_dir = evidence_dir / "render-pack"
    contact_sheet = evidence_dir / "contact-sheet.html"
    command = [
        sys.executable,
        str(HUB_ROOT / "tests" / "fixture_tools" / "render_journal_track_pack.py"),
        "--case",
        fixture_id,
        "--output-dir",
        str(output_dir),
        "--contact-sheet",
        str(contact_sheet),
    ]

    # When: the render pack command completes.
    subprocess.run(command, cwd=HUB_ROOT, check=True)

    # Then: machine-readable summaries and visible captions expose the full track contract.
    summary = read_json_object(output_dir / "summary.json")
    style_delta_summary = read_json_object(output_dir / "style_delta_summary.json")
    validate_style_delta_report(style_delta_summary, expected_tracks=PUBLIC_TRACKS)

    entries = summary["entries"]
    assert isinstance(entries, list)
    assert len(entries) == len(PUBLIC_TRACKS)
    assert {entry["track"] for entry in entries if isinstance(entry, dict)} == set(PUBLIC_TRACKS)
    assert {entry["fixture_class"] for entry in entries if isinstance(entry, dict)} == {fixture_id}

    markup = contact_sheet.read_text(encoding="utf-8")
    assert f"fixture_class={fixture_id}" in markup
    assert "manual_review_needed=" in markup
    assert "dimension_tokens:" in markup
    assert "warnings=" in markup
    assert "unmeasured=" in markup

    image_sources = _image_sources(markup)
    assert image_sources
    assert all(source.startswith("render-pack/") for source in image_sources)
    assert all((contact_sheet.parent / source).is_file() for source in image_sources)
    assert {Path(source).name for source in image_sources} == {
        Path(entry["copied_output_path"]).name for entry in entries if isinstance(entry, dict)
    }


def _basic_series_style_delta_report() -> dict[str, JsonValue]:
    request = StyleDeltaRequest(
        matrix_path=MATRIX_PATH,
        fixture_id="basic_series",
        expected_dir=EXPECTED_ROOT,
        manifest_path=MANIFEST_PATH,
    )
    return build_style_delta_report(request)


def _expected_token_floors(fixture_id: str) -> dict[str, dict[str, JsonValue]]:
    floors: dict[str, dict[str, JsonValue]] = {}
    for track in PUBLIC_TRACKS:
        raw_floors = read_json_object(EXPECTED_ROOT / f"{track}_{fixture_id}.json").get("selected_token_floors")
        assert isinstance(raw_floors, dict)
        floors[track] = raw_floors
    return floors


def _write_render_pack_summary(summary_path: Path, path_key: str, path_value: str) -> None:
    entries = []
    for track in PUBLIC_TRACKS:
        entry: dict[str, JsonValue] = {
            "fixture_class": "path_escape",
            "track": track,
            "status": "ok",
            "manual_review_needed": False,
            "style_summary": {"target_format": track},
        }
        if track == "nature":
            entry[path_key] = path_value
        entries.append(entry)
    summary_path.write_text(
        json.dumps({"schema_version": "journal_track_render_pack/1", "entries": entries}),
        encoding="utf-8",
    )


def _image_sources(markup: str) -> list[str]:
    parser = _ImageSourceParser()
    parser.feed(markup)
    return parser.sources
