from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


def resolve_project_render_workflow_intent(
    config: Mapping[str, Any],
    *,
    workflow_intent_report_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Resolve the workflow intent for the MCP project-render execution surface."""

    return workflow_intent_report_fn(
        config,
        active=True,
        tool_name="figops.render_project_figure",
    )


def resolve_project_render_policy_context(
    arguments: Mapping[str, Any],
    *,
    target_format: str,
    resolve_render_policy_context_fn: Callable[..., Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve the render policy context and keep it mutable for manifest assembly."""

    return dict(
        resolve_render_policy_context_fn(
            arguments,
            target_format=target_format,
        )
    )


def apply_project_render_policy_context(
    style_summary: dict[str, Any],
    policy_context: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Bind resolved policy identity onto the public style summary."""

    validation_target = str(policy_context.get("validation_target") or "")
    render_policy = dict(policy_context["render_policy"])
    style_summary["render_policy"] = render_policy["id"]
    style_summary["validation_target"] = validation_target or None
    return validation_target, render_policy


def decide_project_render_promotion_eligibility(
    *,
    claim_inventory: Mapping[str, Any],
    policy_projections: Sequence[Mapping[str, Any]],
    validation_target: str,
    workflow_intent: Mapping[str, Any],
    manual_review_needed: bool,
) -> dict[str, Any]:
    """Decide review and promotion state after evidence policy projection."""

    projection_ready = (
        len(policy_projections) == 1
        and policy_projections[0].get("status") == "informational"
    )
    policy_review_needed = bool(validation_target) and not projection_ready
    workflow_execution_allowed = workflow_intent.get("execution_allowed") is True
    workflow_review_needed = not workflow_execution_allowed
    manual_review_needed = manual_review_needed or policy_review_needed or workflow_review_needed
    promotion_eligible = bool(
        claim_inventory["promotion_eligible"]
        and validation_target
        and projection_ready
        and workflow_execution_allowed
    )
    return {
        "manual_review_needed": manual_review_needed,
        "policy_review_needed": policy_review_needed,
        "projection_ready": projection_ready,
        "promotion_eligible": promotion_eligible,
        "workflow_execution_allowed": workflow_execution_allowed,
        "workflow_review_needed": workflow_review_needed,
    }


__all__ = [
    "apply_project_render_policy_context",
    "decide_project_render_promotion_eligibility",
    "resolve_project_render_policy_context",
    "resolve_project_render_workflow_intent",
]
