"""Tests for journal compliance provenance registry and report output."""

import json
import re
from pathlib import Path

import pytest

from hub_core.config_parser import ALLOWED_TARGET_FORMATS
from hub_core.journal_specs import (
    JOURNAL_PREFLIGHT_SPECS,
    PREFLIGHT_POLICY_TOKENS,
    list_preflight_tokens,
    list_supported_preflight_targets,
)
from hub_core.style_report import build_style_report, format_style_report
from themes import authentic_style_language
from themes.authentic_style_language import (
    get_authentic_style_language_metadata,
    validate_authentic_style_language_metadata,
)
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT
from themes.style_profiles import get_render_style_tokens

MATRIX_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "specs"
    / "2026-07-04-journal-visual-language-matrix.json"
)
PACKAGE_MATRIX_PATH = (
    Path(__file__).resolve().parent.parent / "themes" / "data" / "journal_visual_language_matrix.json"
)
MATRIX_SOURCE_LABEL = "package:themes/data/journal_visual_language_matrix.json"
PUBLIC_JOURNAL_TRACKS = ("nature", "science", "acs", "rsc", "elsevier", "wiley", "cell")


def test_public_journal_preflight_specs_are_registered():
    expected = {"nature", "science", "acs", "rsc", "elsevier", "wiley", "cell", INTERNAL_STYLE_TARGET_FORMAT}

    assert expected.issubset(set(list_supported_preflight_targets()))
    assert set(list_supported_preflight_targets()).issubset(ALLOWED_TARGET_FORMATS)


def test_preflight_tokens_have_provenance_and_enforcement():
    allowed_provenance = {
        "official_required",
        "official_recommended",
        "publisher_rule_of_thumb",
        "graphhub_assumption",
        "internal_policy",
        "internal_project_style",
    }
    allowed_enforcement = {"error", "warning", "advisory"}

    for target_format in list_supported_preflight_targets():
        for token in list_preflight_tokens(target_format):
            assert token["provenance"] in allowed_provenance
            assert token["enforcement"] in allowed_enforcement
            assert token["source_note"]


def test_preflight_widths_match_legacy_values_for_existing_tracks():
    expected = {
        "nature": 183,
        "science": 170,
        "acs": 171,
        "rsc": 176,
        "elsevier": 190,
    }

    for target_format, max_width_mm in expected.items():
        assert JOURNAL_PREFLIGHT_SPECS[target_format].max_width_mm.value == max_width_mm


def test_style_compliance_tokens_stay_aligned_with_registry_intent():
    expected = {
        "nature": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.25, "max_figure_height_mm": 247.0},
        "science": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
        "acs": {"min_font_size_pt": 4.5, "min_line_width_pt": 0.5, "max_figure_height_mm": 233.0},
        "wiley": {"min_font_size_pt": 5.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
        "cell": {"min_font_size_pt": 6.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 200.0},
        "rsc": {"min_font_size_pt": 7.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 233.0},
        "elsevier": {"min_font_size_pt": 7.0, "min_line_width_pt": 0.5, "max_figure_height_mm": 234.0},
    }

    for target_format, expected_tokens in expected.items():
        tokens, _meta = get_render_style_tokens(target_format, "baseline")
        for key, expected_value in expected_tokens.items():
            assert tokens[key] == expected_value


def test_public_journal_style_language_helper_exposes_matrix_backed_metadata():
    matrix = _read_visual_language_matrix()

    for target_format in PUBLIC_JOURNAL_TRACKS:
        authentic_style_language = get_authentic_style_language_metadata(target_format)

        assert validate_authentic_style_language_metadata(authentic_style_language)
        assert authentic_style_language["matrix_source"] == MATRIX_SOURCE_LABEL
        assert authentic_style_language["matrix_track"] == target_format
        assert authentic_style_language["rationale_category"] == "observed_visual_language"
        assert authentic_style_language["official_claim"] is False
        assert authentic_style_language["rationale"]
        assert authentic_style_language["source_note"]
        assert authentic_style_language["claim_boundary"]
        assert authentic_style_language["observed_visual_language"] == [
            item["item"] for item in matrix["public_tracks"][target_format]["observed_visual_language"]
        ]


def test_packaged_visual_language_matrix_matches_canonical_docs_semantically() -> None:
    docs_matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    package_matrix = json.loads(PACKAGE_MATRIX_PATH.read_text(encoding="utf-8"))

    assert package_matrix == docs_matrix


def test_authentic_style_language_reports_missing_package_matrix_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authentic_style_language, "files", lambda _package: tmp_path, raising=False)

    with pytest.raises(
        authentic_style_language.AuthenticStyleLanguageMatrixMissingError,
        match=re.escape(f"Missing authentic style-language matrix: {MATRIX_SOURCE_LABEL}"),
    ):
        get_authentic_style_language_metadata("nature")


def test_authentic_style_language_reports_corrupt_package_matrix_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "journal_visual_language_matrix.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(authentic_style_language, "files", lambda _package: tmp_path, raising=False)

    with pytest.raises(
        authentic_style_language.AuthenticStyleLanguageMatrixCorruptError,
        match=re.escape(f"Corrupt authentic style-language matrix: {MATRIX_SOURCE_LABEL}"),
    ):
        get_authentic_style_language_metadata("nature")


def test_public_journal_style_language_metadata_rejects_missing_rationale():
    malformed_metadata = dict(get_authentic_style_language_metadata("science"))
    malformed_metadata["rationale"] = ""

    assert not validate_authentic_style_language_metadata(malformed_metadata)


def test_internal_and_policy_tokens_are_not_mislabeled_as_official():
    assert JOURNAL_PREFLIGHT_SPECS[INTERNAL_STYLE_TARGET_FORMAT].max_width_mm.provenance == "internal_project_style"
    assert PREFLIGHT_POLICY_TOKENS["raster_file_size"].provenance == "graphhub_assumption"
    assert PREFLIGHT_POLICY_TOKENS["vector_file_size"].provenance == "internal_policy"


def test_style_report_text_explains_source_and_enforcement():
    report = build_style_report("acs")
    text = format_style_report(report)

    assert "target_format: acs" in text
    assert "acs.max_width_mm" in text
    assert "provenance:" in text
    assert "enforcement:" in text
    assert "source:" in text


def _read_visual_language_matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
