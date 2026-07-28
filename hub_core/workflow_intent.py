from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

INTENT_EXPLORATION = "exploration"
INTENT_EXECUTION = "execution"
INTENT_REVIEW = "review"
INTENT_PROMOTION = "promotion"
WORKFLOW_INTENTS = (INTENT_EXPLORATION, INTENT_EXECUTION, INTENT_REVIEW, INTENT_PROMOTION)

SOURCE_EXPLICIT = "explicit"
SOURCE_ORCHESTRATOR = "orchestrator"
SOURCE_MCP = "mcp"
SOURCE_DIRECT_CSV = "direct_csv"
SOURCE_READ_ONLY = "read_only"
SOURCE_READINESS = "readiness"
SOURCE_LEGACY = "legacy"
WORKFLOW_SOURCES = (
    SOURCE_EXPLICIT, SOURCE_ORCHESTRATOR, SOURCE_MCP, SOURCE_DIRECT_CSV,
    SOURCE_READ_ONLY, SOURCE_READINESS, SOURCE_LEGACY,
)

ORCHESTRATOR_EXECUTION_STEPS = frozenset({"all", "analysis", "plot"})
MCP_EXECUTION_TOOLS = frozenset({"figops.render_project_script", "figops.render_project_figure"})
DIRECT_CSV_TOOLS = frozenset({"figops.render_basic_csv", "figops.render_csv_graph", "figops.render_csv_multipanel"})
READINESS_TOOLS = frozenset({"figops.evaluate_publication_readiness"})
READ_ONLY_TOOLS = frozenset(
    {
        "figops.health", "figops.describe", "figops.list_styles", "figops.list_projects",
        "figops.inspect_project", "figops.validate_project", "figops.collect_artifacts",
        "figops.inspect_data", "figops.audit_artifact",
    }
)
EXECUTION_INTENTS = frozenset({INTENT_EXECUTION})
EXPLORATION_REVIEW_INTENTS = frozenset({INTENT_EXPLORATION, INTENT_REVIEW})
REVIEW_INTENTS = frozenset({INTENT_REVIEW})
ORCHESTRATOR_SOURCES = frozenset({SOURCE_EXPLICIT, SOURCE_ORCHESTRATOR})
MCP_SOURCES = frozenset({SOURCE_EXPLICIT, SOURCE_MCP})
DIRECT_CSV_SOURCES = frozenset({SOURCE_EXPLICIT, SOURCE_DIRECT_CSV})
READ_ONLY_SOURCES = frozenset({SOURCE_EXPLICIT, SOURCE_READINESS, SOURCE_READ_ONLY})
SURFACE_RULES = MappingProxyType(
    {
        SOURCE_ORCHESTRATOR: (INTENT_EXECUTION, EXECUTION_INTENTS, ORCHESTRATOR_SOURCES),
        SOURCE_MCP: (INTENT_EXECUTION, EXECUTION_INTENTS, MCP_SOURCES),
        SOURCE_DIRECT_CSV: (INTENT_EXPLORATION, EXPLORATION_REVIEW_INTENTS, DIRECT_CSV_SOURCES),
        SOURCE_READINESS: (INTENT_REVIEW, REVIEW_INTENTS, READ_ONLY_SOURCES),
        SOURCE_READ_ONLY: (INTENT_REVIEW, REVIEW_INTENTS, READ_ONLY_SOURCES),
    }
)


class WorkflowIntentError(ValueError):
    """A workflow intent or provenance source is outside the closed vocabulary."""


def _normalize_token(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowIntentError(f"{field_name} must be a non-empty string")
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_workflow_intent(value: object) -> str:
    normalized = _normalize_token(value, field_name="workflow intent")
    if normalized not in WORKFLOW_INTENTS:
        raise WorkflowIntentError(f"unknown workflow intent: {value!r}")
    return normalized


def parse_workflow_source(value: object) -> str:
    normalized = _normalize_token(value, field_name="workflow source")
    if normalized not in WORKFLOW_SOURCES:
        raise WorkflowIntentError(f"unknown workflow source: {value!r}")
    return normalized


def _tool_name(value: object) -> str:
    return str(value or "").strip()


def _legacy_surface(tool_name: str, project_status: object, source: str | None) -> bool:
    status = str(project_status or "").strip().lower()
    return status == "legacy" or source == SOURCE_LEGACY or tool_name.startswith("graphhub.")


@dataclass(frozen=True, slots=True)
class WorkflowIntent:
    intent: str | None
    source: str | None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    fail_closed: bool = False
    legacy: bool = False
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.intent is not None and self.intent not in WORKFLOW_INTENTS:
            raise WorkflowIntentError(f"unknown workflow intent: {self.intent!r}")
        if self.source is not None and self.source not in WORKFLOW_SOURCES:
            raise WorkflowIntentError(f"unknown workflow source: {self.source!r}")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def execution_allowed(self) -> bool:
        return self.intent == INTENT_EXECUTION and not self.fail_closed and not self.legacy

    @property
    def promotion_allowed(self) -> bool:
        return self.intent == INTENT_PROMOTION and not self.fail_closed and not self.legacy

    @property
    def read_only(self) -> bool:
        return self.intent == INTENT_REVIEW or self.fail_closed or self.legacy

    @property
    def promotable(self) -> bool:
        return self.promotion_allowed

    @property
    def digest(self) -> str:
        return workflow_intent_digest(self)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "figops-workflow-intent/1",
            "intent": self.intent,
            "source": self.source,
            "provenance": dict(self.provenance),
        }
        payload.update(
            fail_closed=self.fail_closed, legacy=self.legacy, execution_allowed=self.execution_allowed,
            promotion_allowed=self.promotion_allowed, read_only=self.read_only, promotable=self.promotable,
            issues=list(self.issues),
        )
        return payload


def workflow_intent_digest(intent: WorkflowIntent) -> str:
    payload = json.dumps(intent.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fail_closed(
    *,
    intent: str | None,
    source: str | None,
    provenance: Mapping[str, Any],
    issues: tuple[str, ...],
) -> WorkflowIntent:
    return WorkflowIntent(intent=intent, source=source, provenance=provenance, fail_closed=True, issues=issues)


def _surface_intent(
    surface_source: str,
    provenance: Mapping[str, Any],
    requested_intent: str | None,
    requested_source: str | None,
    default_intent: str | None = None,
    compatible_sources: frozenset[str] | None = None,
) -> WorkflowIntent:
    rule_default, compatible_intents, rule_sources = SURFACE_RULES[surface_source]
    default_intent = default_intent or rule_default
    compatible_sources = compatible_sources or rule_sources
    if requested_source is not None and requested_source not in compatible_sources:
        safe_intent = INTENT_REVIEW if requested_source in {SOURCE_READ_ONLY, SOURCE_READINESS} else default_intent
        return _fail_closed(
            intent=safe_intent,
            source=surface_source,
            provenance=provenance,
            issues=(f"requested source {requested_source!r} conflicts with {surface_source!r} surface",),
        )
    if requested_intent is not None and requested_intent not in compatible_intents:
        safe_intent = default_intent if requested_intent == INTENT_EXECUTION else requested_intent
        return _fail_closed(
            intent=safe_intent,
            source=surface_source,
            provenance=provenance,
            issues=(
                f"requested intent {requested_intent!r} conflicts with "
                f"{surface_source!r} surface default {default_intent!r}",
            ),
        )
    return WorkflowIntent(intent=default_intent, source=surface_source, provenance=provenance)


def infer_workflow_intent(
    *,
    active: bool = False,
    step: object = None,
    tool_name: object = None,
    source: object = None,
    requested_intent: object = None,
    project_status: object = None,
) -> WorkflowIntent:
    provenance: dict[str, Any] = {
        "active": bool(active),
        "step": None if step is None else str(step),
        "tool_name": None if tool_name is None else _tool_name(tool_name),
        "requested_intent": None if requested_intent is None else str(requested_intent),
        "requested_source": None if source is None else str(source),
        "project_status": None if project_status is None else str(project_status),
    }
    issues: list[str] = []
    parsed_intent: str | None = None
    parsed_source: str | None = None
    if requested_intent is not None:
        try:
            parsed_intent = parse_workflow_intent(requested_intent)
        except WorkflowIntentError as exc:
            issues.append(str(exc))
    if source is not None:
        try:
            parsed_source = parse_workflow_source(source)
        except WorkflowIntentError as exc:
            issues.append(str(exc))

    tool = provenance["tool_name"] or ""
    if _legacy_surface(tool, project_status, parsed_source):
        return WorkflowIntent(
            intent=INTENT_REVIEW,
            source=SOURCE_LEGACY,
            provenance=provenance,
            legacy=True,
            issues=("legacy workflows are read-only, non-promotable, and never infer execution",),
        )
    if issues:
        return _fail_closed(intent=parsed_intent, source=parsed_source, provenance=provenance, issues=tuple(issues))

    if step is not None:
        try:
            normalized_step = _normalize_token(step, field_name="orchestrator step")
        except WorkflowIntentError as exc:
            return _fail_closed(
                intent=INTENT_REVIEW,
                source=SOURCE_ORCHESTRATOR,
                provenance=provenance,
                issues=(str(exc),),
            )
        if active and normalized_step in ORCHESTRATOR_EXECUTION_STEPS:
            return _surface_intent(SOURCE_ORCHESTRATOR, provenance, parsed_intent, parsed_source)
        issue = f"unknown or inactive orchestrator execution step: {step!r}"
        return _fail_closed(intent=INTENT_REVIEW, source=SOURCE_ORCHESTRATOR, provenance=provenance, issues=(issue,))
    if tool:
        if active and tool in MCP_EXECUTION_TOOLS:
            return _surface_intent(SOURCE_MCP, provenance, parsed_intent, parsed_source)
        if active and tool in DIRECT_CSV_TOOLS:
            return _surface_intent(SOURCE_DIRECT_CSV, provenance, parsed_intent, parsed_source)
        if tool in READINESS_TOOLS:
            return _surface_intent(SOURCE_READINESS, provenance, parsed_intent, parsed_source)
        if tool in READ_ONLY_TOOLS or not active:
            return _surface_intent(SOURCE_READ_ONLY, provenance, parsed_intent, parsed_source)
        return _fail_closed(
            intent=INTENT_REVIEW,
            source=parsed_source,
            provenance=provenance,
            issues=(f"unknown active workflow tool: {tool!r}",),
        )
    if parsed_source in {SOURCE_READ_ONLY, SOURCE_READINESS}:
        return _surface_intent(
            parsed_source,
            provenance,
            parsed_intent,
            parsed_source,
            compatible_sources=frozenset({parsed_source}),
        )
    if parsed_source == SOURCE_DIRECT_CSV:
        return _surface_intent(
            parsed_source,
            provenance,
            parsed_intent,
            parsed_source,
            default_intent=INTENT_EXPLORATION if active else INTENT_REVIEW,
            compatible_sources=frozenset({parsed_source}),
        )
    if parsed_intent is not None and parsed_source in {None, SOURCE_EXPLICIT}:
        return WorkflowIntent(intent=parsed_intent, source=parsed_source or SOURCE_EXPLICIT, provenance=provenance)
    return WorkflowIntent(intent=INTENT_REVIEW, source=parsed_source or SOURCE_READ_ONLY, provenance=provenance)
