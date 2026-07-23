from __future__ import annotations

from typing import Any

from .project_roles import project_status
from .workflow_intent import (
    INTENT_EXECUTION,
    INTENT_PROMOTION,
    INTENT_REVIEW,
    WORKFLOW_INTENTS,
    WorkflowIntentError,
    infer_workflow_intent,
    parse_workflow_intent,
)

ALLOWED_WORKFLOW_INTENTS = set(WORKFLOW_INTENTS)


def compatibility_project_workflow_intent(config: dict) -> str:
    if project_status(config) == "legacy":
        return INTENT_REVIEW
    return INTENT_EXECUTION


def normalize_workflow_defaults(config):
    """Add in-memory workflow defaults without rewriting existing project files."""

    if not isinstance(config, dict):
        return config
    workflow = config.get("workflow")
    default_intent = compatibility_project_workflow_intent(config)
    if workflow is None:
        config["workflow"] = {"intent": default_intent}
        return config
    if not isinstance(workflow, dict):
        return config
    if "intent" not in workflow:
        workflow["intent"] = default_intent
        return config
    try:
        workflow["intent"] = parse_workflow_intent(workflow["intent"])
    except WorkflowIntentError:
        pass
    return config


def workflow_intent(config) -> str | None:
    """Return the normalized declared/default workflow intent, or None when invalid."""

    return workflow_intent_report(config)["intent"]


def workflow_intent_report(
    config,
    *,
    active: bool = False,
    step: object = None,
    tool_name: object = None,
    source: object = None,
) -> dict[str, Any]:
    """Return inspectable workflow intent state with fail-closed execution flags."""

    provenance: dict[str, object] = {"config_source": "compatibility-project-execution"}
    fail_closed = False
    issues: list[str] = []
    intent: str | None

    if not isinstance(config, dict):
        intent = None
        fail_closed = True
        provenance["config_source"] = "invalid-config"
        issues.append("Config root must be a YAML mapping/object.")
    else:
        workflow = config.get("workflow")
        if workflow is None:
            intent = compatibility_project_workflow_intent(config)
        elif not isinstance(workflow, dict):
            intent = None
            fail_closed = True
            provenance["config_source"] = "invalid-config-workflow"
            issues.append("Invalid 'workflow' section (must be a mapping).")
        elif "intent" not in workflow:
            intent = compatibility_project_workflow_intent(config)
        else:
            provenance["config_source"] = "declared"
            try:
                intent = parse_workflow_intent(workflow["intent"])
            except WorkflowIntentError as exc:
                intent = None
                fail_closed = True
                provenance["config_source"] = "declared-invalid"
                issues.append(str(exc))

        if isinstance(config, dict) and project_status(config) == "legacy":
            if intent in {INTENT_EXECUTION, INTENT_PROMOTION}:
                issues.append("legacy projects are read-only, non-promotable, and never execution-enabled")
            intent = INTENT_REVIEW
            provenance["config_source"] = "legacy"
            fail_closed = True

    if intent is not None and not issues and any(value is not None for value in (step, tool_name, source)):
        resolved = infer_workflow_intent(
            active=active,
            step=step,
            tool_name=tool_name,
            source=source,
            requested_intent=intent,
            project_status=project_status(config),
        ).to_dict()
        resolved["provenance"]["config_source"] = provenance["config_source"]
        return resolved

    execution_allowed = intent == INTENT_EXECUTION and not fail_closed
    promotion_allowed = intent == INTENT_PROMOTION and not fail_closed
    return {
        "schema_version": "figops-workflow-intent/1",
        "intent": intent,
        "provenance": provenance,
        "fail_closed": fail_closed,
        "execution_allowed": execution_allowed,
        "promotion_allowed": promotion_allowed,
        "read_only": intent == INTENT_REVIEW or fail_closed,
        "promotable": promotion_allowed,
        "issues": issues,
    }


def validate_workflow_intent_config(errors: list[str], workflow: object, *, project_status: str) -> None:
    if workflow is None:
        workflow = {}
    if not isinstance(workflow, dict):
        errors.append("Invalid 'workflow' section (must be a mapping).")
        return
    if "intent" not in workflow:
        return
    try:
        intent = parse_workflow_intent(workflow.get("intent"))
    except WorkflowIntentError:
        allowed = ", ".join(sorted(ALLOWED_WORKFLOW_INTENTS))
        errors.append(
            f"Invalid workflow.intent: '{workflow.get('intent')}'. Allowed values: {allowed}. "
            "Unknown intents fail closed for execution and remain inspectable."
        )
        return
    if project_status == "legacy" and intent in {INTENT_EXECUTION, INTENT_PROMOTION}:
        errors.append(
            f"project.status 'legacy' cannot declare workflow.intent '{intent}'; "
            "legacy projects are read-only and non-promotable."
        )
