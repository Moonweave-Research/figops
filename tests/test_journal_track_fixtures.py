from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hub_core.mcp import GraphHubMCPServer
from tests.fixture_tools.journal_track_assertions import (
    FIXTURE_CLASSES,
    FIXTURE_ROOT,
    FORBIDDEN_PUBLICATION_CLAIMS,
    HUB_ROOT,
    POLISH_MANIFEST_PATH,
    PUBLIC_JOURNAL_TRACKS,
    SAME_DATASET_CSV_PATH,
    SAME_DATASET_FIXTURE_CLASS,
    TOKEN_FLOOR_KEYS,
    assert_expected_summary_has_schema,
    assert_manifest_is_complete,
    assert_same_dataset_fixture_contract,
    expected_path,
    fixture_entry,
    load_manifest,
    read_json,
)
from themes.style_profiles import get_render_style_tokens


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


def _assert_raw_geometry_contract(geometry_diagnostics) -> dict[str, dict]:
    assert geometry_diagnostics["schema_version"] == "geometry_diagnostics/2"
    assert isinstance(geometry_diagnostics["measurements"], list)
    assert geometry_diagnostics["measurements"]
    assert isinstance(geometry_diagnostics["warnings"], list)

    measurements = {}
    forbidden_policy_fields = {"passed", "severity", "hard_gate", "manual_review_needed", "quality_passed"}
    for measurement in geometry_diagnostics["measurements"]:
        assert forbidden_policy_fields.isdisjoint(measurement)
        assert measurement["metric_id"] not in measurements
        assert measurement["availability"] in {"available", "unavailable"}
        if measurement["availability"] == "available":
            assert "value" in measurement
            assert "reason" not in measurement
        else:
            assert "reason" in measurement
            assert "value" not in measurement
        measurements[measurement["metric_id"]] = measurement
    return measurements


def _measurement_with_prefix(measurements: dict[str, dict], prefix: str) -> dict:
    matches = [measurement for metric_id, measurement in measurements.items() if metric_id.startswith(prefix)]
    assert len(matches) == 1, prefix
    return matches[0]


def _assert_basic_render_matches_expected_summary(result, expected_summary) -> None:
    assert result["status"] == "ok"
    assert result["manual_review_needed"] is False
    assert result["summary"] == "Rendered CSV graph."

    assert result["style_summary"] == expected_summary["style_summary"]
    _assert_raw_geometry_contract(result["geometry_diagnostics"])
    assert result["layout_report"]["schema_version"] == "layout_report/1"
    assert result["layout_report"]["passed"] is None
    assert _selected_token_floors(expected_summary["track"]) == expected_summary["selected_token_floors"]

    manifest = read_json(Path(result["manifest_path"]))
    assert manifest["style_summary"] == result["style_summary"]
    assert manifest["geometry_diagnostics"] == result["geometry_diagnostics"]
    assert manifest["layout_report"]["schema_version"] == "layout_report/1"
    assert manifest["manual_review_needed"] == result["manual_review_needed"]


def _assert_crowded_label_render_surfaces_findings(result, expected_summary) -> None:
    assert result["status"] == "ok"
    assert result["manual_review_needed"] is False
    assert result["summary"] == "Rendered CSV graph."
    assert result["style_summary"] == expected_summary["style_summary"]
    measurements = _assert_raw_geometry_contract(result["geometry_diagnostics"])
    assert result["layout_report"]["schema_version"] == "layout_report/1"
    assert result["layout_report"]["passed"] is None

    tick_overlaps = _measurement_with_prefix(measurements, "tick_label_overlaps[")
    assert tick_overlaps["value"]["x_overlap_pairs"]
    edge_distances = _measurement_with_prefix(measurements, "text_axis_edge_distances[")
    assert edge_distances["value"]["artist_count"] > 0
    pair_iou = _measurement_with_prefix(measurements, "artist_pair_iou[")
    assert any(pair["iou"] > 0 for pair in pair_iou["value"]["pairs"])
    assert any(measurement["availability"] == "unavailable" for measurement in measurements.values())

    result_text = json.dumps(result, sort_keys=True).lower()
    for claim in FORBIDDEN_PUBLICATION_CLAIMS:
        assert claim not in result_text

    manifest = read_json(Path(result["manifest_path"]))
    assert manifest["geometry_diagnostics"] == result["geometry_diagnostics"]
    assert manifest["layout_report"]["schema_version"] == "layout_report/1"
    assert manifest["manual_review_needed"] is False


def _assert_dense_legend_render_surfaces_track_diagnostics(result, expected_summary) -> None:
    assert result["status"] == "ok"
    assert result["manual_review_needed"] is False
    assert result["summary"] == "Rendered CSV graph."

    assert result["style_summary"] == expected_summary["style_summary"]
    measurements = _assert_raw_geometry_contract(result["geometry_diagnostics"])
    assert result["layout_report"]["schema_version"] == "layout_report/1"
    assert not result["layout_report"]["overlaps"]
    assert not result["layout_report"]["clipped"]
    assert _selected_token_floors(expected_summary["track"]) == expected_summary["selected_token_floors"]

    legend_collision = _measurement_with_prefix(measurements, "legend_data_collision[")
    assert legend_collision["availability"] == "available"
    assert isinstance(legend_collision["value"]["overlap_frac"], int | float)
    pair_iou = _measurement_with_prefix(measurements, "artist_pair_iou[")
    assert pair_iou["value"]["candidate_count"] > 0
    assert result["layout_report"]["passed"] is None

    result_text = json.dumps(result, sort_keys=True).lower()
    for claim in FORBIDDEN_PUBLICATION_CLAIMS:
        assert claim not in result_text

    manifest = read_json(Path(result["manifest_path"]))
    assert manifest["geometry_diagnostics"] == result["geometry_diagnostics"]
    assert manifest["layout_report"] == result["layout_report"]
    assert manifest["manual_review_needed"] is False


def test_journal_track_fixture_manifest_is_complete() -> None:
    # Given: the committed journal-track fixture manifest.
    manifest = load_manifest()

    # When / Then: it covers every public track and every required fixture class.
    assert_manifest_is_complete(manifest)


def test_journal_track_expected_summaries_have_required_schema() -> None:
    # Given: the committed journal-track manifest and expected summaries.
    manifest = load_manifest()

    # When / Then: every expected summary exposes the contract later render tasks consume.
    for track in manifest["public_tracks"]:
        for fixture_class in FIXTURE_CLASSES:
            summary = read_json(expected_path(track, fixture_class))
            assert_expected_summary_has_schema(summary, track, fixture_class)


def test_missing_public_track_fixture_is_rejected() -> None:
    # Given: a manifest copy with one public journal track removed.
    manifest = load_manifest()
    incomplete_manifest = copy.deepcopy(manifest)
    incomplete_manifest["public_tracks"] = [track for track in PUBLIC_JOURNAL_TRACKS if track != "cell"]

    # When / Then: validation fails with the exact missing-track contract signal.
    with pytest.raises(AssertionError, match="public_tracks"):
        assert_manifest_is_complete(incomplete_manifest)


def test_missing_same_dataset_user_dogfood_fixture_is_rejected() -> None:
    manifest = load_manifest()
    incomplete_manifest = copy.deepcopy(manifest)
    incomplete_manifest["fixture_classes"] = [
        entry for entry in manifest["fixture_classes"] if entry["id"] != SAME_DATASET_FIXTURE_CLASS
    ]

    with pytest.raises(AssertionError):
        assert_manifest_is_complete(incomplete_manifest)


def test_same_dataset_user_dogfood_fixture_rejects_per_track_data() -> None:
    manifest = load_manifest()
    fixture = copy.deepcopy(fixture_entry(manifest, SAME_DATASET_FIXTURE_CLASS))
    fixture["csv_path"] = {track: SAME_DATASET_CSV_PATH for track in PUBLIC_JOURNAL_TRACKS}

    with pytest.raises(AssertionError, match="one shared CSV path"):
        assert_same_dataset_fixture_contract(fixture)


def test_malformed_expected_summary_is_rejected() -> None:
    # Given: a valid expected summary with a required token floor removed.
    summary = read_json(expected_path("nature", "basic_series"))
    malformed_summary = copy.deepcopy(summary)
    del malformed_summary["selected_token_floors"]["min_line_width_pt"]

    # When / Then: validation rejects the malformed expected JSON schema.
    with pytest.raises(AssertionError):
        assert_expected_summary_has_schema(malformed_summary, "nature", "basic_series")


def test_polish_fixture_manifest_registers_journal_track_pack() -> None:
    # Given: the committed polish fixture registry.
    polish_manifest = read_json(POLISH_MANIFEST_PATH)
    acceptance_command = (
        "python hub_uv.py run python -m pytest "
        "tests/test_journal_style_delta.py tests/test_journal_track_fixtures.py -q"
    )

    # When / Then: the journal pack entry is registered with the focused fixture/delta command.
    entries = {entry["id"]: entry for entry in polish_manifest["fixtures"]}
    journal_entry = entries["journal-track-fixture-pack"]
    assert journal_entry["automation_level"] == "automated"
    assert journal_entry["acceptance_command"] == acceptance_command


def test_basic_journal_track_renders_match_expected_summaries(tmp_path: Path) -> None:
    # Given: the readable basic-series fixture and committed expected summaries.
    manifest = load_manifest()
    fixture = fixture_entry(manifest, "basic_series")

    # When / Then: every public journal track renders with manifest-backed style and diagnostics contracts.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = read_json(expected_path(track, "basic_series"))
        _assert_basic_render_matches_expected_summary(result, expected_summary)


def test_basic_render_rejects_mismatched_expected_token_floor(tmp_path: Path) -> None:
    # Given: a valid basic-series render and a corrupted expected token floor.
    manifest = load_manifest()
    fixture = fixture_entry(manifest, "basic_series")
    result = _render_journal_fixture(tmp_path / "nature", fixture, "nature")
    expected_summary = read_json(expected_path("nature", "basic_series"))
    corrupted_summary = copy.deepcopy(expected_summary)
    corrupted_summary["selected_token_floors"]["min_font_size_pt"] += 1

    # When / Then: the render contract rejects the mismatched expected summary.
    with pytest.raises(AssertionError):
        _assert_basic_render_matches_expected_summary(result, corrupted_summary)


def test_crowded_label_journal_tracks_surface_geometry_findings(tmp_path: Path) -> None:
    # Given: the crowded-label stress fixture and committed expected summaries.
    manifest = load_manifest()
    fixture = fixture_entry(manifest, "crowded_labels")

    # When / Then: each public journal track reports measured findings and unmeasured states explicitly.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = read_json(expected_path(track, "crowded_labels"))
        _assert_crowded_label_render_surfaces_findings(result, expected_summary)


def test_dense_legend_journal_tracks_surface_track_specific_diagnostics(tmp_path: Path) -> None:
    # Given: the dense-legend stress fixture and committed expected summaries.
    manifest = load_manifest()
    fixture = fixture_entry(manifest, "dense_legend")

    # When / Then: each public journal track exposes dense-legend and tick-label diagnostics explicitly.
    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = read_json(expected_path(track, "dense_legend"))
        _assert_dense_legend_render_surfaces_track_diagnostics(result, expected_summary)


def test_same_dataset_user_dogfood_renders_all_public_tracks(tmp_path: Path) -> None:
    manifest = load_manifest()
    fixture = fixture_entry(manifest, SAME_DATASET_FIXTURE_CLASS)
    assert_same_dataset_fixture_contract(fixture)

    for track in PUBLIC_JOURNAL_TRACKS:
        result = _render_journal_fixture(tmp_path / track, fixture, track)
        expected_summary = read_json(expected_path(track, SAME_DATASET_FIXTURE_CLASS))
        _assert_basic_render_matches_expected_summary(result, expected_summary)
        assert "manual_review_needed" in result
        assert isinstance(result["manual_review_needed"], bool)
