from __future__ import annotations

import pytest

from hub_core.workflow_intent import (
    DIRECT_CSV_TOOLS,
    INTENT_EXECUTION,
    INTENT_EXPLORATION,
    INTENT_PROMOTION,
    INTENT_REVIEW,
    MCP_EXECUTION_TOOLS,
    ORCHESTRATOR_EXECUTION_STEPS,
    READ_ONLY_TOOLS,
    READINESS_TOOLS,
    SOURCE_DIRECT_CSV,
    SOURCE_LEGACY,
    SOURCE_MCP,
    SOURCE_ORCHESTRATOR,
    SOURCE_READ_ONLY,
    SOURCE_READINESS,
    WorkflowIntent,
    WorkflowIntentError,
    infer_workflow_intent,
    parse_workflow_intent,
    parse_workflow_source,
)


def test_strict_parser_normalizes_known_intent_and_source_only() -> None:
    assert parse_workflow_intent(" Execution ") == INTENT_EXECUTION
    assert parse_workflow_intent("review") == INTENT_REVIEW
    assert parse_workflow_source("read-only") == SOURCE_READ_ONLY

    with pytest.raises(WorkflowIntentError, match="unknown workflow intent"):
        parse_workflow_intent("run")
    with pytest.raises(WorkflowIntentError, match="unknown workflow source"):
        parse_workflow_source("notebook")


@pytest.mark.parametrize("step", sorted(ORCHESTRATOR_EXECUTION_STEPS))
def test_orchestrator_active_execution_steps_infer_execution(step: str) -> None:
    intent = infer_workflow_intent(active=True, step=step)

    assert intent.intent == INTENT_EXECUTION
    assert intent.source == SOURCE_ORCHESTRATOR
    assert intent.execution_allowed is True
    assert intent.read_only is False


def test_inactive_or_unknown_orchestrator_step_fails_closed() -> None:
    inactive = infer_workflow_intent(active=False, step="plot")
    unknown = infer_workflow_intent(active=True, step="publish")

    for intent in (inactive, unknown):
        assert intent.intent == INTENT_REVIEW
        assert intent.source == SOURCE_ORCHESTRATOR
        assert intent.execution_allowed is False
        assert intent.fail_closed is True
        assert intent.issues


@pytest.mark.parametrize("tool_name", sorted(MCP_EXECUTION_TOOLS))
def test_mcp_project_render_surfaces_infer_execution(tool_name: str) -> None:
    intent = infer_workflow_intent(active=True, tool_name=tool_name)

    assert intent.intent == INTENT_EXECUTION
    assert intent.source == SOURCE_MCP
    assert intent.execution_allowed is True
    assert intent.promotable is False


@pytest.mark.parametrize("tool_name", sorted(DIRECT_CSV_TOOLS))
def test_direct_csv_surfaces_infer_exploration(tool_name: str) -> None:
    intent = infer_workflow_intent(active=True, tool_name=tool_name)

    assert intent.intent == INTENT_EXPLORATION
    assert intent.source == SOURCE_DIRECT_CSV
    assert intent.execution_allowed is False
    assert intent.promotion_allowed is False
    assert intent.read_only is False


@pytest.mark.parametrize("tool_name", sorted(READ_ONLY_TOOLS | READINESS_TOOLS))
def test_read_only_and_readiness_surfaces_have_no_execution_intent(tool_name: str) -> None:
    intent = infer_workflow_intent(active=True, tool_name=tool_name)

    assert intent.intent == INTENT_REVIEW
    assert intent.source in {SOURCE_READ_ONLY, SOURCE_READINESS}
    assert intent.execution_allowed is False
    assert intent.read_only is True


def test_explicit_intent_does_not_override_known_surface_defaults() -> None:
    csv_intent = infer_workflow_intent(
        active=True,
        tool_name="figops.render_csv_graph",
        requested_intent=INTENT_EXECUTION,
    )
    orchestrator_intent = infer_workflow_intent(
        active=True,
        step="all",
        requested_intent=INTENT_EXPLORATION,
    )
    readiness_intent = infer_workflow_intent(
        active=True,
        source="readiness",
        requested_intent=INTENT_EXECUTION,
    )

    assert csv_intent.intent == INTENT_EXPLORATION
    assert csv_intent.source == SOURCE_DIRECT_CSV
    assert csv_intent.fail_closed is True
    assert orchestrator_intent.intent == INTENT_EXPLORATION
    assert orchestrator_intent.source == SOURCE_ORCHESTRATOR
    assert orchestrator_intent.fail_closed is True
    assert readiness_intent.intent == INTENT_REVIEW
    assert readiness_intent.source == SOURCE_READINESS
    assert readiness_intent.fail_closed is True


@pytest.mark.parametrize("requested_intent", (INTENT_REVIEW, INTENT_PROMOTION))
@pytest.mark.parametrize("tool_name", sorted(MCP_EXECUTION_TOOLS))
def test_active_project_render_non_execution_intent_conflicts_fail_closed(
    tool_name: str,
    requested_intent: str,
) -> None:
    intent = infer_workflow_intent(
        active=True,
        tool_name=tool_name,
        requested_intent=requested_intent,
    )

    assert intent.intent == requested_intent
    assert intent.source == SOURCE_MCP
    assert intent.execution_allowed is False
    assert intent.promotion_allowed is False
    assert intent.fail_closed is True
    assert "conflicts" in intent.issues[0]


@pytest.mark.parametrize("requested_intent", (INTENT_REVIEW, INTENT_PROMOTION))
def test_active_orchestrator_render_non_execution_intent_conflicts_fail_closed(requested_intent: str) -> None:
    intent = infer_workflow_intent(active=True, step="plot", requested_intent=requested_intent)

    assert intent.intent == requested_intent
    assert intent.source == SOURCE_ORCHESTRATOR
    assert intent.execution_allowed is False
    assert intent.promotion_allowed is False
    assert intent.fail_closed is True
    assert "conflicts" in intent.issues[0]


@pytest.mark.parametrize(
    ("tool_name", "source", "requested_intent", "expected_intent", "expected_source"),
    (
        ("figops.render_project_figure", SOURCE_READ_ONLY, INTENT_EXECUTION, INTENT_REVIEW, SOURCE_MCP),
        ("figops.render_project_figure", SOURCE_READINESS, INTENT_EXECUTION, INTENT_REVIEW, SOURCE_MCP),
        ("figops.render_csv_graph", None, INTENT_PROMOTION, INTENT_PROMOTION, SOURCE_DIRECT_CSV),
        ("figops.evaluate_publication_readiness", None, INTENT_EXECUTION, INTENT_REVIEW, SOURCE_READINESS),
    ),
)
def test_source_surface_and_intent_conflict_matrix_is_deterministic(
    tool_name: str,
    source: str | None,
    requested_intent: str,
    expected_intent: str,
    expected_source: str,
) -> None:
    intent = infer_workflow_intent(
        active=True,
        tool_name=tool_name,
        source=source,
        requested_intent=requested_intent,
    )

    assert intent.intent == expected_intent
    assert intent.source == expected_source
    assert intent.execution_allowed is False
    assert intent.promotion_allowed is False
    assert intent.fail_closed is True
    assert "conflicts" in intent.issues[0]


def test_legacy_status_overrides_active_execution_surfaces() -> None:
    for kwargs in (
        {"active": True, "step": "all"},
        {"active": True, "tool_name": "figops.render_project_figure"},
        {"active": True, "tool_name": "graphhub.render_project_figure"},
    ):
        intent = infer_workflow_intent(**kwargs, project_status="legacy")

        assert intent.intent == INTENT_REVIEW
        assert intent.source == SOURCE_LEGACY
        assert intent.legacy is True
        assert intent.execution_allowed is False
        assert intent.promotable is False
        assert intent.read_only is True


def test_unknown_intent_or_source_is_inspectable_and_fails_closed_for_execution() -> None:
    intent = infer_workflow_intent(active=True, requested_intent="execution", source="notebook")
    unknown_intent = infer_workflow_intent(active=True, requested_intent="run", source="mcp")

    assert intent.intent == INTENT_EXECUTION
    assert intent.source is None
    assert intent.execution_allowed is False
    assert intent.fail_closed is True
    assert intent.provenance["requested_source"] == "notebook"
    assert intent.issues == ("unknown workflow source: 'notebook'",)

    assert unknown_intent.intent is None
    assert unknown_intent.source == SOURCE_MCP
    assert unknown_intent.execution_allowed is False
    assert unknown_intent.fail_closed is True
    assert unknown_intent.provenance["requested_intent"] == "run"


def test_explicit_promotion_is_closed_and_digest_is_deterministic() -> None:
    left = infer_workflow_intent(requested_intent=INTENT_PROMOTION)
    right = WorkflowIntent(
        intent=INTENT_PROMOTION,
        source="explicit",
        provenance={"requested_intent": INTENT_PROMOTION},
    )

    assert left.intent == INTENT_PROMOTION
    assert left.promotion_allowed is True
    assert left.digest == left.digest
    assert len(left.digest) == 64
    assert right.digest == right.digest
