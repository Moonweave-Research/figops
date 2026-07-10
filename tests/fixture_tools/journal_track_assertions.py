from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from hub_core.config_style import ALLOWED_TARGET_FORMATS

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

HUB_ROOT: Final = Path(__file__).resolve().parent.parent.parent
FIXTURE_ROOT: Final = HUB_ROOT / "tests" / "fixtures" / "journal_tracks"
MANIFEST_PATH: Final = FIXTURE_ROOT / "manifest.json"
EXPECTED_ROOT: Final = FIXTURE_ROOT / "expected"
PUBLIC_JOURNAL_TRACKS: Final = ("nature", "science", "acs", "rsc", "elsevier", "wiley", "cell")
SAME_DATASET_FIXTURE_CLASS: Final = "same_dataset_user_dogfood"
SAME_DATASET_CSV_PATH: Final = "csv/same_dataset_user_dogfood.csv"
FIXTURE_CLASSES: Final = ("basic_series", "crowded_labels", "dense_legend", SAME_DATASET_FIXTURE_CLASS)
EXPECTED_SUMMARY_SCHEMA: Final = "journal_track_expected_summary/1"
MANIFEST_SCHEMA: Final = "journal_track_fixtures/1"
TOKEN_FLOOR_KEYS: Final = ("min_font_size_pt", "min_line_width_pt", "max_figure_height_mm")
SCIENCE_COMPACT_LABEL_MAX_CHARS: Final = 12
EXPECTED_CROWDED_LABEL_FINDINGS: Final = (
    "tick_label_overlaps",
    "tick_label_crowding",
    "point_annotation_overlaps",
    "text_axis_edge_proximity",
    "point_label_skips",
)
EXPECTED_DENSE_LEGEND_CHECKS: Final = (
    "legend_data_collision",
    "legend_internal_overlaps",
    "legend_marker_consistency",
)
FORBIDDEN_PUBLICATION_CLAIMS: Final = ("publishable", "publication-ready")
POLISH_MANIFEST_PATH: Final = HUB_ROOT / "docs" / "specs" / "polish-fixture-manifest.json"
ACCEPTANCE_COMMAND: Final = (
    "python hub_uv.py run python -m pytest "
    "tests/test_journal_track_fixtures.py::test_journal_track_fixture_manifest_is_complete "
    "tests/test_journal_track_fixtures.py::test_journal_track_expected_summaries_have_required_schema "
    "tests/test_journal_track_fixtures.py::test_missing_public_track_fixture_is_rejected -q"
)


def read_json(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def load_manifest(path: Path = MANIFEST_PATH) -> JsonObject:
    return read_json(path)


def expected_path(track: str, fixture_class: str) -> Path:
    return EXPECTED_ROOT / f"{track}_{fixture_class}.json"


def assert_manifest_is_complete(manifest: JsonObject, fixture_root: Path = FIXTURE_ROOT) -> None:
    assert manifest["schema_version"] == MANIFEST_SCHEMA
    assert tuple(manifest["public_tracks"]) == PUBLIC_JOURNAL_TRACKS, "public_tracks"
    assert set(PUBLIC_JOURNAL_TRACKS).issubset(ALLOWED_TARGET_FORMATS)

    fixture_entries = manifest["fixture_classes"]
    assert isinstance(fixture_entries, list)
    fixtures_by_id = {entry["id"]: entry for entry in fixture_entries}
    assert set(fixtures_by_id) == set(FIXTURE_CLASSES)
    assert_same_dataset_fixture_contract(fixtures_by_id[SAME_DATASET_FIXTURE_CLASS])

    for fixture_class, entry in fixtures_by_id.items():
        csv_path = fixture_root / entry["csv_path"]
        assert csv_path.is_file(), f"missing CSV fixture for {fixture_class}: {csv_path}"
        assert entry["expected_summary_pattern"] == f"expected/{{track}}_{fixture_class}.json"
        for track in PUBLIC_JOURNAL_TRACKS:
            assert expected_path(track, fixture_class).is_file(), f"missing expected summary: {track}/{fixture_class}"


def assert_same_dataset_fixture_contract(entry: JsonObject) -> None:
    assert isinstance(entry["csv_path"], str), "same-dataset fixture must use one shared CSV path"
    assert entry["csv_path"] == SAME_DATASET_CSV_PATH

    render_arguments = entry["render_arguments"]
    assert isinstance(render_arguments, dict)
    assert render_arguments.get("title", "") == ""
    assert isinstance(render_arguments["x_axis_label"], str)
    assert isinstance(render_arguments["y_axis_label"], str)
    assert len(render_arguments["x_axis_label"]) <= SCIENCE_COMPACT_LABEL_MAX_CHARS
    assert len(render_arguments["y_axis_label"]) <= SCIENCE_COMPACT_LABEL_MAX_CHARS

    forbidden_per_track_keys = (
        "csv_paths",
        "per_track_csv_paths",
        "track_csv_paths",
        "per_track_render_arguments",
        "track_render_arguments",
        "track_overrides",
    )
    for key in forbidden_per_track_keys:
        assert key not in entry
        assert key not in render_arguments


def assert_expected_summary_has_schema(summary: JsonObject, expected_track: str, expected_fixture_class: str) -> None:
    assert summary["schema_version"] == EXPECTED_SUMMARY_SCHEMA
    assert summary["track"] == expected_track
    assert summary["fixture_class"] == expected_fixture_class

    style_summary = summary["style_summary"]
    assert isinstance(style_summary, dict)
    assert style_summary["target_format"] == expected_track
    assert style_summary["profile"] == "baseline"

    token_floors = summary["selected_token_floors"]
    assert isinstance(token_floors, dict)
    assert set(token_floors) == set(TOKEN_FLOOR_KEYS)
    assert all(isinstance(token_floors[key], int | float) for key in TOKEN_FLOOR_KEYS)

    geometry_diagnostics = summary["geometry_diagnostics"]
    layout_report = summary["layout_report"]
    assert isinstance(geometry_diagnostics, dict)
    assert isinstance(layout_report, dict)
    assert geometry_diagnostics["schema_version"] == "geometry_diagnostics/1"
    assert layout_report["schema_version"] == "layout_report/1"


def fixture_entry(manifest: JsonObject, fixture_class: str) -> JsonObject:
    fixture_entries = manifest["fixture_classes"]
    assert isinstance(fixture_entries, list)
    matches = [entry for entry in fixture_entries if isinstance(entry, dict) and entry["id"] == fixture_class]
    assert len(matches) == 1
    return matches[0]
