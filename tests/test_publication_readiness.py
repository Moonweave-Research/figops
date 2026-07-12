from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.publication_readiness import (
    canonical_json_bytes,
    evaluate_publication_readiness,
    evidence_digest,
    render_readiness_json,
    render_readiness_markdown,
)


def _geometry(*checks: dict) -> dict:
    return {"schema_version": "geometry_diagnostics/1", "checks": list(checks), "passed": True}


def test_clean_evidence_requires_human_review_and_never_approves() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "tick_label_overlaps", "passed": True})},
        project_id="project",
        figure_id="Fig2b",
        required_evidence=("geometry_diagnostics",),
    )

    assert report["readiness_status"] == "needs_review"
    assert report["manual_review_required"] is True
    assert "approved" not in json.dumps(report)
    assert report["findings"] == []


@pytest.mark.parametrize("passed", [False, None])
def test_hard_geometry_failure_or_unmeasured_result_blocks(passed: bool | None) -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "artists_outside_figure", "passed": passed})}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["rubric_id"] == "FQ-H2"
    assert report["findings"][0]["severity"] == "hard"


def test_advisory_geometry_failure_needs_revision() -> None:
    payload = _geometry({"name": "tick_label_crowding", "passed": False})
    payload["passed"] = False
    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["rubric_id"] == "FQ-A2"


def test_unknown_geometry_check_is_conservatively_reviewed() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "future_check", "passed": True})}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "GEOMETRY_CHECK_UNKNOWN"


def test_failed_calculation_takes_precedence_over_advisory() -> None:
    geometry = _geometry({"name": "tick_label_crowding", "passed": False})
    geometry["passed"] = False
    report = evaluate_publication_readiness(
        {
            "geometry_diagnostics": geometry,
            "calculation_checks": {
                "schema_version": "1.0",
                "checks": [{"name": "mass balance", "status": "failed", "message": "drift"}]
            },
        }
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["severity"] == "hard"


def test_missing_required_evidence_fails_closed() -> None:
    report = evaluate_publication_readiness({}, required_evidence=("geometry_diagnostics",))

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "REQUIRED_EVIDENCE_MISSING"


def test_digest_is_key_order_path_and_line_ending_stable() -> None:
    first = {"b": Path("results/figure.png"), "a": "line 1\r\nline 2"}
    second = {"a": "line 1\nline 2", "b": "results/figure.png"}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert evidence_digest(first) == evidence_digest(second)


def test_digest_normalizes_unambiguous_relative_path_strings() -> None:
    assert evidence_digest({"x": "results\\Fig.png"}) == evidence_digest({"x": "results/Fig.png"})


def test_digest_preserves_ordinary_backslash_text() -> None:
    assert canonical_json_bytes({"note": r"keep a \ backslash"}) != canonical_json_bytes(
        {"note": "keep a / backslash"}
    )


def test_digest_changes_when_evidence_changes() -> None:
    assert evidence_digest({"passed": True}) != evidence_digest({"passed": False})


def test_non_finite_numbers_and_non_string_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="NaN"):
        evidence_digest({"value": float("nan")})
    with pytest.raises(TypeError, match="keys"):
        evidence_digest({1: "invalid"})  # type: ignore[dict-item]


def test_json_and_markdown_reports_are_deterministic_and_bounded() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "tick_label_overlaps", "passed": True})}
    )

    assert render_readiness_json(report) == render_readiness_json(report)
    markdown = render_readiness_markdown(report)
    assert markdown == render_readiness_markdown(report)
    assert "Automatic evaluation does not constitute publication approval." in markdown
    assert "No automatic findings. Human review is still required." in markdown


@pytest.mark.parametrize("passed", [None, "true", 0, False])
def test_summary_sources_only_accept_literal_true(passed: object) -> None:
    report = evaluate_publication_readiness({"visual_preflight_status": {"passed": passed}})

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "VISUAL_PREFLIGHT_STATUS_FAILED"


def test_geometry_unsupported_schema_blocks() -> None:
    payload = _geometry({"name": "tick_label_overlaps", "passed": True})
    payload["schema_version"] = "geometry_diagnostics/2"

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "GEOMETRY_SCHEMA_UNSUPPORTED"


def test_duplicate_geometry_check_names_block() -> None:
    check = {"name": "legend_data_collision", "passed": True}
    report = evaluate_publication_readiness({"geometry_diagnostics": _geometry(check, check)})

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "GEOMETRY_CHECK_DUPLICATE"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "2.0", "checks": []},
        {"schema_version": "1.0", "checks": None},
        {"schema_version": "1.0", "checks": ["invalid"]},
    ],
)
def test_invalid_calculation_contract_blocks(payload: dict) -> None:
    report = evaluate_publication_readiness({"calculation_checks": payload})

    assert report["readiness_status"] == "blocked"


def test_manual_review_false_does_not_override_calculation_failure() -> None:
    report = evaluate_publication_readiness(
        {
            "calculation_checks": {
                "schema_version": "1.0",
                "checks": [
                    {
                        "name": "balance",
                        "status": "failed",
                        "manual_review_needed": False,
                    }
                ],
            }
        }
    )

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "CALCULATION_FAILED" for item in report["findings"])


@pytest.mark.parametrize("summary", [False, None])
def test_unexplained_geometry_summary_blocks(summary: bool | None) -> None:
    payload = _geometry({"name": "tick_label_overlaps", "passed": True})
    payload["passed"] = summary

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_SUMMARY_INCONSISTENT" for item in report["findings"])


def test_geometry_true_summary_with_failed_check_blocks_as_inconsistent() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "tick_label_crowding", "passed": False})}
    )

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_SUMMARY_INCONSISTENT" for item in report["findings"])


@pytest.mark.parametrize("status", [None, "warning", "unknown", 0])
def test_unknown_calculation_status_blocks(status: object) -> None:
    report = evaluate_publication_readiness(
        {"calculation_checks": {"schema_version": "1.0", "checks": [{"status": status}]}}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "CALCULATION_STATUS_INVALID"


def test_skipped_calculation_needs_revision() -> None:
    report = evaluate_publication_readiness(
        {"calculation_checks": {"schema_version": "1.0", "checks": [{"status": "skipped"}]}}
    )

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["code"] == "CALCULATION_SKIPPED"


def test_layout_report_requires_supported_schema_and_literal_true() -> None:
    invalid_schema = evaluate_publication_readiness(
        {"layout_report": {"schema_version": "layout_report/2", "passed": True}}
    )
    invalid_pass = evaluate_publication_readiness(
        {"layout_report": {"schema_version": "layout_report/1", "passed": None}}
    )

    assert invalid_schema["readiness_status"] == "blocked"
    assert invalid_schema["findings"][0]["code"] == "LAYOUT_REPORT_SCHEMA_UNSUPPORTED"
    assert invalid_pass["readiness_status"] == "blocked"


def test_informational_failure_is_reported_without_changing_state() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "legend_data_collision", "passed": False})}
    )

    assert report["readiness_status"] == "needs_review"
    assert report["findings"][0]["severity"] == "info"


@pytest.mark.parametrize("passed", [None, "false", 0])
def test_informational_check_requires_literal_boolean(passed: object) -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "legend_data_collision", "passed": passed})}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "GEOMETRY_CHECK_PASSED_INVALID"


def test_report_exposes_target_format_and_stable_gates_in_both_renderings() -> None:
    report = evaluate_publication_readiness(
        {
            "style_summary": {"target_format": "nature"},
            "visual_preflight_status": {"passed": True},
        }
    )

    assert report["target_format"] == "nature"
    assert report["gates"] == [
        {"source": "visual_preflight_status", "outcome": "passed", "evidence_ref": "visual_preflight_status"}
    ]
    assert '"gates"' in render_readiness_json(report)
    markdown = render_readiness_markdown(report)
    assert "## Gates" in markdown
    assert "- Target format: `nature`" in markdown
    assert "`visual_preflight_status`: `passed` (evidence: `visual_preflight_status`)" in markdown
