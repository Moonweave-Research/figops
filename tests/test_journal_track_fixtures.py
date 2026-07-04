from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hub_core.config_style import ALLOWED_TARGET_FORMATS
from hub_core.mcp import GraphHubMCPServer
from themes.style_profiles import get_render_style_tokens

HUB_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = HUB_ROOT / "tests" / "fixtures" / "journal_tracks"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"
PUBLIC_JOURNAL_TRACKS = ("nature", "science", "acs", "rsc", "elsevier", "wiley", "cell")
FIXTURE_CLASSES = ("basic_series", "crowded_labels", "dense_legend")
EXPECTED_SUMMARY_SCHEMA = "journal_track_expected_summary/1"
MANIFEST_SCHEMA = "journal_track_fixtures/1"
TOKEN_FLOOR_KEYS = ("min_font_size_pt", "min_line_width_pt", "max_figure_height_mm")
EXPECTED_CROWDED_LABEL_FINDINGS = (
    "tick_label_overlaps",
    "tick_label_crowding",
    "point_annotation_overlaps",
    "text_axis_edge_proximity",
    "point_label_skips",
)
EXPECTED_DENSE_LEGEND_CHECKS = (
    "legend_data_collision",
    "legend_internal_overlaps",
    "legend_marker_consistency",
)
EXPECTED_DENSE_LEGEND_WARNINGS = {
    "science": ("tick_label_overlaps", "tick_label_crowding"),
}
FORBIDDEN_PUBLICATION_CLAIMS = ("publishable", "publication-ready")
POLISH_MANIFEST_PATH = HUB_ROOT / "docs" / "specs" / "polish-fixture-manifest.json"
ACCEPTANCE_COMMAND = (
    "python hub_uv.py run python -m pytest "
    "tests/test_journal_track_fixtures.py::test_journal_track_fixture_manifest_is_complete "
    "tests/test_journal_track_fixtures.py::test_journal_track_expected_summaries_have_required_schema "
    "tests/test_journal_track_fixtures.py::test_missing_public_track_fixture_is_rejected -q"
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest(path: Path = MANIFEST_PATH):
    return _read_json(path)


def _expected_path(track: str, fixture_class: str) -> Path:
    return EXPECTED_ROOT / f"{track}_{fixture_class}.json"


def _assert_manifest_is_complete(manifest, fixture_root: Path = FIXTURE_ROOT) -> None:
    assert manifest["schema_version"] == MANIFEST_SCHEMA
    assert tuple(manifest["public_tracks"]) == PUBLIC_JOURNAL_TRACKS, "public_tracks"
    assert set(PUBLIC_JOURNAL_TRACKS).issubset(ALLOWED_TARGET_FORMATS)

    fixtures_by_id = {entry["id"]: entry for entry in manifest["fixture_classes"]}
    assert set(fixtures_by_id) == set(FIXTURE_CLASSES)

    for fixture_class, entry in fixtures_by_id.items():
        csv_path = fixture_root / entry["csv_path"]
        assert csv_path.is_file(), f"missing CSV fixture for {fixture_class}: {csv_path}"
        assert entry["expected_summary_pattern"] == f"expected/{{track}}_{fixture_class}.json"
        for track in PUBLIC_JOURNAL_TRACKS:
            assert _expected_path(track, fixture_class).is_file(), f"missing expected summary: {track}/{fixture_class}"


def _assert_expected_summary_has_schema(summary, expected_track: str, expected_fixture_class: str) -> None:
    assert summary["schema_version"] == EXPECTED_SUMMARY_SCHEMA
    assert summary["track"] == expected_track
    assert summary["fixture_class"] == expected_fixture_class

    style_summary = summary["style_summary"]
    assert style_summary["target_format"] == expected_track
    assert style_summary["profile"] == "baseline"

    token_floors = summary["selected_token_floors"]
    assert set(token_floors) == set(TOKEN_FLOOR_KEYS)
    assert all(isinstance(token_floors[key], int | float) for key in TOKEN_FLOOR_KEYS)

    assert summary["geometry_diagnostics"]["schema_version"] == "geometry_diagnostics/1"
    assert summary["layout_report"]["schema_version"] == "layout_report/1"


def _fixture_entry(manifest, fixture_class: str):
    matches = [entry for entry in manifest["fixture_classes"] if entry["id"] == fixture_class]
    assert len(matches) == 1
    return matches[0]


def _render_journal_fixture(tmp_path: Path, fixture, track: str):
    server = GraphHubMCPServer(research_root=HUB_ROOT, runtime_root=tmp_path / "runtime")
    arguments = dict(fixture["render_arguments"])
    arguments.update(
        {
            "data_path": str((FIXTURE_ROOT / fixture["csv_path"]).resolve()),
            "target_format": track,
            "profile": "baseline",
            "output_format": "png",
            "overwrite": True,
            "job_id": f"pytest-basic-{track}",
        }
    )
    response = server.call_tool("figops.render_csv_graph", arguments)
    return response["structuredContent"]


def _selected_token_floors(track: str):
    tokens, _metadata = get_render_style_tokens(track, "baseline")
    return {key: tokens[key] for key in TOKEN_FLOOR_KEYS}


def _assert_basic_render_matches_expected_summary(result, expected_summary) -> None:
    assert result["status"] in {"ok", "warning"}
    if result["status"] == "warning":
        assert result["manual_review_needed"] is True
        assert result["summary"] != "Rendered CSV graph."

    assert result["style_summary"] == expected_summary["style_summary"]
    assert result["geometry_diagnostics"]["schema_version"] == "geometry_diagnostics/1"
    assert result["layout_report"]["schema_version"] == "layout_report/1"
    assert _selected_token_floors(expected_summary["track"]) == expected_summary["selected_token_floors"]

    manifest = _read_json(Path(result["manifest_path"]))
    assert manifest["style_summary"] == result["style_summary"]
    assert manifest["geometry_diagnostics"]["schema_version"] == "geometry_diagnostics/1"
    assert manifest["layout_report"]["schema_version"] == "layout_report/1"
    assert manifest["manual_review_needed"] == result["manual_review_needed"]


def _checks_by_name(geometry_diagnostics):
    checks = {}
    for check in geometry_diagnostics["checks"]:
        checks.setdefault(check["name"], []).append(check)
    return checks


def _assert_crowded_label_render_surfaces_findings(result, expected_summary) -> None:
    assert result["status"] == "warning"
    assert result["manual_review_needed"] is True
    assert result["style_summary"] == expected_summary["style_summary"]
    assert result["geometry_diagnostics"]["schema_version"] == "geometry_diagnostics/1"
    assert result["layout_report"]["schema_version"] == "layout_report/1"

    checks_by_name = _checks_by_name(result["geometry_diagnostics"])
    for check_name in EXPECTED_CROWDED_LABEL_FINDINGS:
        assert any(check["passed"] is False for check in checks_by_name[check_name]), check_name

    unmeasured = [check for check in result["geometry_diagnostics"]["checks"] if check["passed"] is None]
    assert unmeasured, "crowded-label stress should expose at least one unmeasured check"
    measured_passes = [check["name"] for check in result["geometry_diagnostics"]["checks"] if check["passed"] is True]
    assert all(check["name"] not in measured_passes for check in unmeasured)

    result_text = json.dumps(result, sort_keys=True).lower()
    for claim in FORBIDDEN_PUBLICATION_CLAIMS:
        assert claim not in result_text

    manifest = _read_json(Path(result["manifest_path"]))
    assert manifest["geometry_diagnostics"] == result["geometry_diagnostics"]
    assert manifest["layout_report"]["schema_version"] == "layout_report/1"
    assert manifest["manual_review_needed"] is True


def _assert_dense_legend_render_surfaces_track_diagnostics(result, expected_summary) -> None:
    track = expected_summary["track"]
    expected_warning_checks = EXPECTED_DENSE_LEGEND_WARNINGS.get(track, ())
    if expected_warning_checks:
        assert result["status"] == "warning"
        assert result["manual_review_needed"] is True
        assert result["summary"] != "Rendered CSV graph."
    else:
        assert result["status"] == "ok"
        assert result["manual_review_needed"] is False
        assert result["summary"] == "Rendered CSV graph."

    assert result["style_summary"] == expected_summary["style_summary"]
    assert result["geometry_diagnostics"]["schema_version"] == "geometry_diagnostics/1"
    assert result["layout_report"]["schema_version"] == "layout_report/1"
    assert not result["layout_report"]["overlaps"]
    assert not result["layout_report"]["clipped"]
    assert _selected_token_floors(expected_summary["track"]) == expected_summary["selected_token_floors"]

    checks_by_name = _checks_by_name(result["geometry_diagnostics"])
    for check_name in EXPECTED_DENSE_LEGEND_CHECKS:
        assert any(check["passed"] is True for check in checks_by_name[check_name]), check_name

    failed_checks = [check["name"] for check in result["geometry_diagnostics"]["checks"] if check["passed"] is False]
    assert tuple(failed_checks) == expected_warning_checks
    assert result["layout_report"]["passed"] is (not expected_warning_checks)

    result_text = json.dumps(result, sort_keys=True).lower()
    for claim in FORBIDDEN_PUBLICATION_CLAIMS:
        assert claim not in result_text

    manifest = _read_json(Path(result["manifest_path"]))
    assert manifest["geometry_diagnostics"] == result["geometry_diagnostics"]
    assert manifest["layout_report"] == result["layout_report"]
    assert manifest["manual_review_needed"] is bool(expected_warning_checks)


def test_journal_track_fixture_manifest_is_complete() -> None:
    # Given: the committed journal-track fixture manifest.
    manifest = _load_manifest()

    # When / Then: it covers every public track and every required fixture class.
    _assert_manifest_is_complete(manifest)


def test_journal_track_expected_summaries_have_required_schema() -> None:
    # Given: the committed journal-track manifest and expected summaries.
    manifest = _load_manifest()

    # When / Then: every expected summary exposes the contract later render tasks consume.
    for track in manifest["public_tracks"]:
        for fixture_class in FIXTURE_CLASSES:
            summary = _read_json(_expected_path(track, fixture_class))
            _assert_expected_summary_has_schema(summary, track, fixture_class)


def test_missing_public_track_fixture_is_rejected() -> None:
    # Given: a manifest copy with one public journal track removed.
    manifest = _load_manifest()
    incomplete_manifest = copy.deepcopy(manifest)
    incomplete_manifest["public_tracks"] = [track for track in PUBLIC_JOURNAL_TRACKS if track != "cell"]

    # When / Then: validation fails with the exact missing-track contract signal.
    with pytest.raises(AssertionError, match="public_tracks"):
        _assert_manifest_is_complete(incomplete_manifest)


def test_malformed_expected_summary_is_rejected() -> None:
    # Given: a valid expected summary with a required token floor removed.
    summary = _read_json(_expected_path("nature", "basic_series"))
    malformed_summary = copy.deepcopy(summary)
    del malformed_summary["selected_token_floors"]["min_line_width_pt"]

    # When / Then: validation rejects the malformed expected JSON schema.
    with pytest.raises(AssertionError):
        _assert_expected_summary_has_schema(malformed_summary, "nature", "basic_series")


def test_polish_fixture_manifest_registers_journal_track_pack() -> None:
    # Given: the committed polish fixture registry.
    polish_manifest = _read_json(POLISH_MANIFEST_PATH)

    # When / Then: the journal pack entry is registered with the exact Task 1 acceptance command.
    entries = {entry["id"]: entry for entry in polish_manifest["fixtures"]}
    journal_entry = entries["journal-track-fixture-pack"]
    assert journal_entry["automation_level"] == "automated"
    assert journal_entry["acceptance_command"] == ACCEPTANCE_COMMAND


def test_basic_journal_track_renders_match_expected_summaries(tmp_path: Path) -> None:
    # Given: the readable basic-series fixture and committed expected summaries.
    manifest = _load_manifest()
    fixture = _fixture_entry(manifest, "basic_series")

    # When / Then: every public journal track renders with manifest-backed style and diagnostics contracts.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = _read_json(_expected_path(track, "basic_series"))
        _assert_basic_render_matches_expected_summary(result, expected_summary)


def test_basic_render_rejects_mismatched_expected_token_floor(tmp_path: Path) -> None:
    # Given: a valid basic-series render and a corrupted expected token floor.
    manifest = _load_manifest()
    fixture = _fixture_entry(manifest, "basic_series")
    result = _render_journal_fixture(tmp_path / "nature", fixture, "nature")
    expected_summary = _read_json(_expected_path("nature", "basic_series"))
    corrupted_summary = copy.deepcopy(expected_summary)
    corrupted_summary["selected_token_floors"]["min_font_size_pt"] += 1

    # When / Then: the render contract rejects the mismatched expected summary.
    with pytest.raises(AssertionError):
        _assert_basic_render_matches_expected_summary(result, corrupted_summary)


def test_crowded_label_journal_tracks_surface_geometry_findings(tmp_path: Path) -> None:
    # Given: the crowded-label stress fixture and committed expected summaries.
    manifest = _load_manifest()
    fixture = _fixture_entry(manifest, "crowded_labels")

    # When / Then: each public journal track reports measured findings and unmeasured states explicitly.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = _read_json(_expected_path(track, "crowded_labels"))
        _assert_crowded_label_render_surfaces_findings(result, expected_summary)


def test_dense_legend_journal_tracks_surface_track_specific_diagnostics(tmp_path: Path) -> None:
    # Given: the dense-legend stress fixture and committed expected summaries.
    manifest = _load_manifest()
    fixture = _fixture_entry(manifest, "dense_legend")

    # When / Then: each public journal track exposes dense-legend and tick-label diagnostics explicitly.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = _read_json(_expected_path(track, "dense_legend"))
        _assert_dense_legend_render_surfaces_track_diagnostics(result, expected_summary)
