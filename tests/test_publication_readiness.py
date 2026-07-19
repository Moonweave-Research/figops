from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hub_core.publication_geometry_readiness import (
    geometry_findings,
    policy_projection_findings,
)
from hub_core.publication_readiness import (
    canonical_json_bytes,
    evaluate_publication_readiness,
    evidence_digest,
    render_readiness_json,
    render_readiness_markdown,
)


def _raw_finding(**kwargs: object) -> dict[str, object]:
    return dict(kwargs)


def _geometry(*checks: dict) -> dict:
    return {"schema_version": "geometry_diagnostics/1", "checks": list(checks), "passed": True}


def _geometry_v2(*measurements: dict) -> dict:
    return {
        "schema_version": "geometry_diagnostics/2",
        "measurements": list(measurements),
        "warnings": [],
    }


def _v2_envelope(*measurements: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "2.0",
        "producer": {"status": "warning", "kind": "test-render", "version": "1.0"},
        "measurements": list(measurements),
        "policy_projections": [],
        "artifacts": {
            "status": "unavailable",
            "reason": "no artifact in readiness unit fixture",
            "entries": [],
        },
        "provenance": {
            "status": "skipped",
            "reason": "no artifact in readiness unit fixture",
            "unavailable_fields": [
                "input_sha256",
                "config_sha256",
                "script_sha256",
                "environment_sha256",
                "output_sha256",
            ],
        },
        "data_contract_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "not selected",
        },
        "calculation_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "not selected",
        },
        "exact_reproducibility": None,
        "visual_comparison": None,
    }


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


def test_hard_geometry_failure_blocks() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "artists_outside_figure", "passed": False})}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["rubric_id"] == "FQ-H2"
    assert report["findings"][0]["severity"] == "hard"


def test_required_unmeasured_geometry_blocks_only_when_policy_requires_it() -> None:
    payload = _geometry({"name": "artists_outside_figure", "passed": None})
    payload["passed"] = None
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": payload},
        required_diagnostic_ids=("artists_outside_figure",),
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "GEOMETRY_REQUIRED_DIAGNOSTIC_UNAVAILABLE"


def test_advisory_geometry_failure_needs_revision() -> None:
    payload = _geometry({"name": "tick_label_crowding", "passed": False})
    payload["passed"] = False
    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["rubric_id"] == "FQ-A2"


@pytest.mark.parametrize(
    "metric_id",
    [
        "tick_label_overlaps",
        "blank_area_ratio",
        "marker_marker_overlaps",
        "font_size_token_drift",
    ],
)
def test_legacy_aesthetic_failures_are_compatibility_advisories(metric_id: str) -> None:
    payload = _geometry({"name": metric_id, "passed": False})
    payload["passed"] = False

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["severity"] == "major"


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
                "checks": [{"name": "mass balance", "status": "failed", "message": "drift"}],
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
    assert canonical_json_bytes({"note": r"keep a \ backslash"}) != canonical_json_bytes({"note": "keep a / backslash"})


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


def test_geometry_v2_rejects_legacy_checks_shape() -> None:
    payload = _geometry({"name": "tick_label_overlaps", "passed": True})
    payload["schema_version"] = "geometry_diagnostics/2"

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_EVIDENCE_INVALID" for item in report["findings"])


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


@pytest.mark.parametrize("status", [None, "unknown", 0])
def test_unknown_calculation_status_blocks(status: object) -> None:
    report = evaluate_publication_readiness(
        {"calculation_checks": {"schema_version": "1.0", "checks": [{"status": status}]}}
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "CALCULATION_STATUS_INVALID"


def test_warning_calculation_status_is_supported() -> None:
    report = evaluate_publication_readiness(
        {"calculation_checks": {"schema_version": "1.0", "checks": [{"status": "warning"}]}}
    )

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["code"] == "CALCULATION_WARNING"


def test_skipped_calculation_needs_revision() -> None:
    report = evaluate_publication_readiness(
        {"calculation_checks": {"schema_version": "1.0", "checks": [{"status": "skipped"}]}}
    )

    assert report["readiness_status"] == "needs_revision"
    assert report["findings"][0]["code"] == "CALCULATION_SKIPPED"


def test_layout_report_requires_supported_schema_but_ignores_legacy_aggregate() -> None:
    invalid_schema = evaluate_publication_readiness(
        {"layout_report": {"schema_version": "layout_report/2", "passed": True}}
    )
    unavailable_aggregate = evaluate_publication_readiness(
        {"layout_report": {"schema_version": "layout_report/1", "passed": None}}
    )

    assert invalid_schema["readiness_status"] == "blocked"
    assert invalid_schema["findings"][0]["code"] == "LAYOUT_REPORT_SCHEMA_UNSUPPORTED"
    assert unavailable_aggregate["readiness_status"] == "needs_review"


def test_layout_report_hard_gates_explicit_render_error_not_aggregate_false() -> None:
    aggregate_only = evaluate_publication_readiness(
        {"layout_report": {"schema_version": "layout_report/1", "passed": False}}
    )
    render_error = evaluate_publication_readiness(
        {
            "layout_report": {
                "schema_version": "layout_report/1",
                "passed": None,
                "render_errors": [{"stage": "PLOT"}],
            }
        }
    )

    assert aggregate_only["readiness_status"] == "needs_review"
    assert render_error["readiness_status"] == "blocked"
    assert render_error["findings"][0]["code"] == "LAYOUT_RENDER_ERROR"


def test_informational_failure_is_reported_without_changing_state() -> None:
    payload = _geometry({"name": "legend_data_collision", "passed": False})
    payload["passed"] = False
    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "needs_review"
    assert report["findings"][0]["severity"] == "info"


@pytest.mark.parametrize("passed", [None, "false", 0])
def test_informational_check_requires_literal_boolean(passed: object) -> None:
    payload = _geometry({"name": "legend_data_collision", "passed": passed})
    if passed is None:
        payload["passed"] = None
    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    if passed is None:
        assert report["readiness_status"] == "needs_review"
        assert report["findings"][0]["code"] == "GEOMETRY_DIAGNOSTIC_UNAVAILABLE"
    else:
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


def test_raw_geometry_v2_available_measurement_is_evidence_not_a_verdict() -> None:
    payload = _geometry_v2(
        {
            "metric_id": "tick_label_overlaps[axis=0]",
            "availability": "available",
            "value": {"x_overlap_pairs": [], "y_overlap_pairs": []},
            "unit": "structured",
            "scope": "axis=0",
        }
    )

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "needs_review"
    assert report["findings"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("passed", False),
        ("severity", "hard"),
        ("policy_id", "journal-science"),
        ("threshold", 0.9),
        ("min_font_size_pt", 5.0),
        ("font_offenders", []),
        ("verdict", "blocked"),
    ],
)
def test_raw_geometry_v2_rejects_recursive_policy_fields(field: str, value: object) -> None:
    payload = _geometry_v2(
        {
            "metric_id": "style_geometry_observations",
            "availability": "available",
            "value": {"observed": {field: value}},
            "unit": "structured",
            "scope": "figure",
        }
    )

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_RAW_POLICY_FIELD_FORBIDDEN" for item in report["findings"])


def test_raw_geometry_v2_rejects_aggregate_passed_instead_of_trusting_it() -> None:
    payload = _geometry_v2()
    payload["passed"] = True

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_RAW_POLICY_FIELD_FORBIDDEN" for item in report["findings"])


def test_raw_geometry_v2_rejects_unknown_decision_field() -> None:
    payload = _geometry_v2(
        {
            "metric_id": "tick_label_overlaps[axis=0]",
            "availability": "available",
            "value": {"x_overlap_pairs": []},
            "decision": "pass",
        }
    )

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_MEASUREMENT_FIELD_UNKNOWN" for item in report["findings"])


def test_raw_geometry_v2_optional_and_required_unavailable_are_distinct() -> None:
    payload = _geometry_v2(
        {
            "metric_id": "artists_outside_figure[axis=0]",
            "availability": "unavailable",
            "unit": "structured",
            "scope": "axis=0",
            "reason": "renderer extent unavailable",
        }
    )

    optional = evaluate_publication_readiness({"geometry_diagnostics": payload})
    required = evaluate_publication_readiness(
        {"geometry_diagnostics": payload},
        required_diagnostic_ids=("artists_outside_figure",),
    )

    assert optional["readiness_status"] == "needs_review"
    assert optional["findings"][0]["code"] == "GEOMETRY_DIAGNOSTIC_UNAVAILABLE"
    assert required["readiness_status"] == "blocked"
    assert required["findings"][0]["code"] == "GEOMETRY_REQUIRED_DIAGNOSTIC_UNAVAILABLE"


def test_raw_geometry_v2_malformed_unavailable_measurement_fails_closed() -> None:
    payload = _geometry_v2(
        {
            "metric_id": "artists_outside_figure[axis=0]",
            "availability": "unavailable",
            "value": {"overflow_count": 0},
            "reason": "renderer unavailable",
        }
    )

    report = evaluate_publication_readiness({"geometry_diagnostics": payload})

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "GEOMETRY_MEASUREMENT_UNAVAILABLE_INVALID" for item in report["findings"])


def test_selected_objective_policy_projection_can_hard_gate_raw_measurement() -> None:
    metric_id = "artists_outside_figure[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"overflow_count": 1, "layout_locked": True},
            "unit": "structured",
            "scope": "axis=0",
        }
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"clipping": "block"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
            "resolved": {"clipping": {"value": "block", "source": "resolved_policy"}},
            "findings": [
                {
                    "code": "FIGURE_CLIPPING_DETECTED",
                    "metric_id": metric_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "A locked-layout artist exceeds the figure bounds.",
                }
            ],
            "status": "blocked",
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == ["publication-readiness-v2"]
    assert any(gate["source"] == "policy_projection" and gate["outcome"] == "blocked" for gate in report["gates"])
    finding = next(item for item in report["findings"] if item["code"] == "FIGURE_CLIPPING_DETECTED")
    assert finding["severity"] == "hard"
    assert finding["evidence_ref"] == metric_id
    assert finding["rubric_id"] == "publication-readiness-v2@2"


def test_unselected_policy_projection_and_aggregate_status_do_not_gate() -> None:
    metric_id = "artists_outside_figure[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"overflow_count": 0, "layout_locked": True},
            "unit": "structured",
            "scope": "axis=0",
        }
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"overlap": "review"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
            "resolved": {"clipping": {"value": "block", "source": "policy"}},
            "status": "blocked",
        }
    ]

    report = evaluate_publication_readiness(envelope)

    assert report["readiness_status"] == "needs_review"
    assert report["applied_policies"] == []
    assert not any(item["source"] == "policy_projection" for item in report["findings"])


def test_selected_policy_cannot_promote_aesthetic_measurement_to_hard_gate() -> None:
    metric_id = "tick_label_overlaps[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"x_overlap_pairs": [[0, 1]], "y_overlap_pairs": []},
            "unit": "structured",
            "scope": "axis=0",
        }
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"overlap": "review"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
            "resolved": {"overlap": {"value": "review", "source": "resolved_policy"}},
            "findings": [
                {
                    "code": "TICK_OVERLAP",
                    "metric_id": metric_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "Tick labels overlap.",
                }
            ],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "needs_revision"
    finding = next(item for item in report["findings"] if item["source"] == "policy_projection")
    assert finding["severity"] == "major"
    assert finding["code"] == "TICK_OVERLAP_AESTHETIC_ADVISORY"


def test_text_edge_proximity_is_hybrid_advisory_even_when_projection_requests_hard() -> None:
    metric_id = "text_axis_edge_proximity[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"findings": [{"clipped": True, "min_distance_px": -1.0}]},
            "scope": "axis=0",
        }
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"edge_proximity": "review"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
            "resolved": {"edge_proximity": {"value": "review", "source": "resolved_policy"}},
            "findings": [
                {
                    "code": "TEXT_EDGE_PROXIMITY",
                    "metric_id": metric_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "Text intersects an axis edge.",
                }
            ],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "needs_revision"
    finding = next(item for item in report["findings"] if item["source"] == "policy_projection")
    assert finding["severity"] == "major"
    assert finding["code"] == "TEXT_EDGE_PROXIMITY_AESTHETIC_ADVISORY"


def test_selected_projection_requires_resolved_policy_snapshot() -> None:
    metric_id = "artists_outside_figure[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"overflow_count": 0},
        }
    )
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == []
    assert any(item["code"] == "POLICY_RESOLUTION_MISSING" for item in report["findings"])


def test_legacy_policy_id_without_validated_projection_is_unapplied_and_blocks() -> None:
    report = evaluate_publication_readiness(
        {"geometry_diagnostics": _geometry({"name": "tick_label_overlaps", "passed": True})},
        policy_ids=("ghost-policy",),
    )

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == []
    assert any(item["code"] == "POLICY_SELECTION_UNVALIDATED" for item in report["findings"])


def test_v2_resolved_policy_without_matching_projection_is_unapplied_and_blocks() -> None:
    envelope = _v2_envelope()
    envelope["resolved_policy"] = {
        "id": "ghost-policy",
        "version": "1",
        "source": "caller",
        "parameters": {},
    }

    report = evaluate_publication_readiness(envelope, policy_ids=("ghost-policy",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == []
    assert any(item["code"] == "POLICY_PROJECTION_MISSING" for item in report["findings"])


def test_projection_local_resolution_cannot_override_canonical_snapshot() -> None:
    metric_id = "style_geometry_observations"
    envelope = _v2_envelope({"id": metric_id, "availability": "available", "value": {"figure_height_mm": 200.0}})
    envelope["resolved_policy"] = {
        "id": "journal-science",
        "version": "1",
        "source": "caller",
        "parameters": {"max_height_mm": 234.0},
    }
    envelope["policy_projections"] = [
        {
            "id": "journal-science",
            "version": "1",
            "measurement_refs": [metric_id],
            "resolved": {"max_height_mm": {"value": 180.0, "source": "resolved_policy"}},
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("journal-science",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == []
    assert any(item["code"] == "POLICY_PROJECTION_RESOLUTION_CONFLICT" for item in report["findings"])


def test_top_level_resolved_policy_can_resolve_selected_projection() -> None:
    metric_id = "style_geometry_observations"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "available",
            "value": {"figure_height_mm": 250.0, "font_sizes": [], "line_widths": []},
            "unit": "structured",
            "scope": "figure",
        }
    )
    envelope["resolved_policy"] = {
        "id": "journal-science",
        "version": "1",
        "source": "caller",
        "parameters": {"max_figure_height_mm": 234.0},
    }
    envelope["policy_projections"] = [
        {
            "id": "journal-science",
            "version": "1",
            "measurement_refs": [metric_id],
            "findings": [
                {
                    "code": "FIGURE_HEIGHT_EXCEEDS_MAXIMUM",
                    "metric_id": metric_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "Observed height exceeds the selected journal maximum.",
                }
            ],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("journal-science",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == ["journal-science"]
    assert any(item["code"] == "FIGURE_HEIGHT_EXCEEDS_MAXIMUM" for item in report["findings"])


def test_forged_policy_finding_on_unavailable_measurement_blocks() -> None:
    metric_id = "artists_outside_figure[axis=0]"
    envelope = _v2_envelope(
        {
            "id": metric_id,
            "availability": "unavailable",
            "reason": "renderer unavailable",
        }
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"clipping": "block"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [metric_id],
            "resolved": {"clipping": {"value": "block", "source": "resolved_policy"}},
            "findings": [
                {
                    "code": "FORGED_CLIPPING",
                    "metric_id": metric_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "Invented from unavailable evidence.",
                }
            ],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "blocked"
    assert any(item["code"] == "POLICY_FINDING_METRIC_UNAVAILABLE" for item in report["findings"])


def test_invalid_projection_is_rejected_atomically_without_applying_valid_prefix() -> None:
    available_id = "tick_label_overlaps[axis=0]"
    unavailable_id = "geometry.optional_probe"
    envelope = _v2_envelope(
        {
            "id": available_id,
            "availability": "available",
            "value": 1,
            "unit": "count",
            "scope": "axis=0",
        },
        {
            "id": unavailable_id,
            "availability": "unavailable",
            "reason": "optional probe was not installed",
        },
    )
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"overlap": "review"},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [available_id, unavailable_id],
            "findings": [
                {
                    "code": "TICK_OVERLAP",
                    "metric_id": available_id,
                    "severity": "advisory",
                    "outcome": "needs_revision",
                    "message": "Tick labels overlap.",
                },
                {
                    "code": "OPTIONAL_PROBE_BLOCK",
                    "metric_id": unavailable_id,
                    "severity": "hard",
                    "outcome": "blocked",
                    "message": "This finding has no available raw evidence.",
                },
            ],
        }
    ]

    report = evaluate_publication_readiness(envelope, policy_ids=("publication-readiness-v2",))

    assert report["readiness_status"] == "blocked"
    assert report["applied_policies"] == []
    assert any(item["code"] == "POLICY_FINDING_METRIC_UNAVAILABLE" for item in report["findings"])
    assert not any(item["code"] == "TICK_OVERLAP" for item in report["findings"])


def test_geometry_helper_directly_returns_validated_measurement_index() -> None:
    payload = _geometry_v2(
        {
            "metric_id": "artists_outside_figure[axis=0]",
            "availability": "available",
            "value": {"overflow_count": 0, "layout_locked": True},
            "scope": "axis=0",
        }
    )

    findings, measurements = geometry_findings(payload, finding=_raw_finding)

    assert findings == []
    assert set(measurements) == {"artists_outside_figure[axis=0]"}


def test_policy_projection_helper_directly_demotes_aesthetic_hard_finding() -> None:
    metric_id = "font_size_token_drift"
    measurements = {
        metric_id: {
            "id": metric_id,
            "availability": "available",
            "value": {"observed_font_sizes_pt": [5.5, 6.0]},
        }
    }
    envelope = {
        "resolved_policy": {
            "id": "publication-readiness-v2",
            "version": "2",
            "source": "caller",
            "parameters": {"font_tokens": "review"},
        },
        "policy_projections": [
            {
                "id": "publication-readiness-v2",
                "version": "2",
                "measurement_refs": [metric_id],
                "resolved": {"font_tokens": {"value": "review", "source": "resolved_policy"}},
                "findings": [
                    {
                        "code": "FONT_TOKEN_DRIFT",
                        "metric_id": metric_id,
                        "severity": "hard",
                        "outcome": "blocked",
                        "message": "Observed font sizes differ from preferred tokens.",
                    }
                ],
            }
        ],
    }

    findings, applied = policy_projection_findings(
        envelope,
        measurements,
        policy_ids=("publication-readiness-v2",),
        finding=_raw_finding,
    )

    assert applied == ["publication-readiness-v2"]
    assert findings[0]["severity"] == "major"
    assert findings[0]["code"] == "FONT_TOKEN_DRIFT_AESTHETIC_ADVISORY"
