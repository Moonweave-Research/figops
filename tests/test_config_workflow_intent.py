from __future__ import annotations

import copy
from pathlib import Path

import yaml

from hub_core.config_parser import (
    normalize_workflow_defaults,
    validate_config,
    workflow_intent,
    workflow_intent_report,
)
from hub_core.project_layout import build_scaffold_config_text
from hub_core.workflow_intent import INTENT_EXECUTION, INTENT_EXPLORATION, INTENT_REVIEW, infer_workflow_intent


def _minimal_config() -> dict:
    return {
        "project": {"name": "Workflow Intent Demo"},
        "visual_style": {"target_format": "neutral"},
    }


def test_active_project_without_declared_workflow_normalizes_to_execution() -> None:
    config = normalize_workflow_defaults(copy.deepcopy(_minimal_config()))

    assert validate_config(config) == []
    assert config["workflow"]["intent"] == INTENT_EXECUTION
    assert workflow_intent(config) == INTENT_EXECUTION
    report = workflow_intent_report(config)
    assert report["execution_allowed"] is True
    assert report["provenance"]["config_source"] == "declared"


def test_unknown_workflow_intent_fails_closed_but_remains_inspectable() -> None:
    config = _minimal_config()
    config["workflow"] = {"intent": "run"}

    errors = validate_config(config)
    report = workflow_intent_report(config)

    assert any("Invalid workflow.intent" in error for error in errors)
    assert report["intent"] is None
    assert report["execution_allowed"] is False
    assert report["fail_closed"] is True
    assert report["provenance"]["config_source"] == "declared-invalid"
    assert report["issues"] == ["unknown workflow intent: 'run'"]


def test_legacy_projects_normalize_to_read_only_non_promotable_intent() -> None:
    config = _minimal_config()
    config["project"]["status"] = "legacy"
    normalized = normalize_workflow_defaults(copy.deepcopy(config))
    explicit_execution = copy.deepcopy(config)
    explicit_execution["workflow"] = {"intent": INTENT_EXECUTION}

    assert normalized["workflow"]["intent"] == INTENT_REVIEW
    report = workflow_intent_report(normalized)
    assert report["intent"] == INTENT_REVIEW
    assert report["execution_allowed"] is False
    assert report["promotable"] is False
    assert report["read_only"] is True
    assert any("legacy" in error for error in validate_config(explicit_execution))


def test_explicit_project_draft_intent_conflicts_with_execution_surface_without_mutating_config() -> None:
    config = normalize_workflow_defaults(copy.deepcopy(_minimal_config()))
    config["workflow"]["intent"] = INTENT_EXPLORATION

    report = workflow_intent_report(config, active=True, step="plot")

    assert config["workflow"]["intent"] == INTENT_EXPLORATION
    assert validate_config(config) == []
    assert report["intent"] == INTENT_EXPLORATION
    assert report["source"] == "orchestrator"
    assert report["execution_allowed"] is False
    assert report["fail_closed"] is True
    assert report["provenance"]["config_source"] == "declared"
    assert "conflicts with 'orchestrator' surface" in report["issues"][0]


def test_direct_csv_and_read_only_compatibility_intents_never_enable_execution() -> None:
    csv_intent = infer_workflow_intent(active=True, tool_name="figops.render_csv_graph")
    read_only_intent = infer_workflow_intent(active=True, tool_name="figops.inspect_project")

    assert csv_intent.intent == INTENT_EXPLORATION
    assert csv_intent.execution_allowed is False
    assert csv_intent.promotable is False
    assert read_only_intent.intent == INTENT_REVIEW
    assert read_only_intent.execution_allowed is False
    assert read_only_intent.read_only is True


def test_project_templates_and_scaffolded_config_declare_execution_intent() -> None:
    hub_path = Path(__file__).resolve().parents[1]
    template_paths = [
        hub_path / "project_config_template.yaml",
        hub_path / "hub_core" / "templates" / "project_config_template.yaml",
    ]

    for template_path in template_paths:
        config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        assert config["workflow"]["intent"] == INTENT_EXECUTION
        assert validate_config(config) == []

    scaffolded = yaml.safe_load(
        build_scaffold_config_text(hub_path, "Scaffold Workflow Demo", "neutral", font_scale=1.0)
    )
    assert scaffolded["workflow"]["intent"] == INTENT_EXECUTION
    assert validate_config(scaffolded) == []
