"""Thin v2 render adapters over the strengthened compatibility kernels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS
from hub_core.mcp.render_response import one_render_response
from hub_core.mcp.tools.render_csv import McpRenderCsvMixin
from hub_core.mcp.tools.render_project import McpRenderProjectMixin
from themes.style_profiles import DEFAULT_PROFILE

_BASIC_ARGS: Final = frozenset(
    {
        "data_path",
        "x",
        "y",
        "plot_type",
        "series",
        "facet",
        "labels",
        "style_policy",
        "output_format",
        "job_id",
        "overwrite",
    }
)
_PROJECT_ARGS: Final = frozenset(
    {"project_id", "project_path", "figure_id", "figure_output", "job_id", "overwrite"}
)
_LABEL_ARGS: Final = frozenset({"title", "x_axis", "y_axis"})
_BASIC_PLOT_TYPES: Final = frozenset({"scatter", "line", "bar"})


class McpRenderV2Mixin:
    """Keep rendering expressive through project scripts and compact for quick charts."""

    def render_basic_csv(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tool_name = "figops.render_basic_csv"
        guarded = self._v2_write_guard(tool_name, arguments)
        if guarded is not None:
            return guarded
        try:
            self._closed_arguments(arguments, _BASIC_ARGS)
            labels = arguments.get("labels", {})
            if not isinstance(labels, Mapping):
                raise ValueError("labels must be an object")
            self._closed_arguments(dict(labels), _LABEL_ARGS, prefix="labels")
            plot_type = str(arguments.get("plot_type") or "scatter").strip().lower()
            if plot_type not in _BASIC_PLOT_TYPES:
                raise ValueError("plot_type is outside the basic lane; use a declared project script")
            style_policy = str(arguments.get("style_policy") or "nature").strip().lower()
            if style_policy not in ALLOWED_TARGET_FORMATS:
                raise ValueError("style_policy is not a supported explicit journal/style policy")
            output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
            if output_format not in ALLOWED_OUTPUT_FORMATS:
                raise ValueError("output_format is unsupported")
            compatibility_args = {
                "data_path": arguments.get("data_path"),
                "x_column": arguments.get("x"),
                "y_column": arguments.get("y"),
                "plot_type": plot_type,
                "series_column": arguments.get("series") or "",
                "facet_column": arguments.get("facet") or "",
                "title": labels.get("title") or "",
                "x_axis_label": labels.get("x_axis") or arguments.get("x"),
                "y_axis_label": labels.get("y_axis") or arguments.get("y"),
                "target_format": style_policy,
                "profile": DEFAULT_PROFILE,
                "output_format": output_format,
                "job_id": arguments.get("job_id"),
                "overwrite": bool(arguments.get("overwrite", False)),
                "label_transform": "raw",
                "compliance_mode": "validate",
                "declutter_mode": "none",
                "dry_run": False,
            }
        except ValueError as exc:
            return one_render_response(
                tool_name,
                {
                    "status": "error",
                    "summary": "Basic CSV render request is invalid.",
                    "errors": [str(exc)],
                    "failure_stage": "CONTRACT",
                    "resolution_hint": "Use the compact quick-chart fields or a declared project script.",
                },
            )
        result = McpRenderCsvMixin.render_csv_graph(self, compatibility_args)
        return one_render_response(tool_name, result)

    def render_project_script(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tool_name = "figops.render_project_script"
        guarded = self._v2_write_guard(tool_name, arguments)
        if guarded is not None:
            return guarded
        try:
            self._closed_arguments(arguments, _PROJECT_ARGS)
        except ValueError as exc:
            return one_render_response(
                tool_name,
                {
                    "status": "error",
                    "summary": "Project script render request is invalid.",
                    "errors": [str(exc)],
                    "failure_stage": "CONTRACT",
                    "resolution_hint": (
                        "Select a configured figure; code, commands, arguments, and interpreters are forbidden."
                    ),
                },
            )
        compatibility_args = dict(arguments)
        compatibility_args["dry_run"] = False
        result = McpRenderProjectMixin.render_project_figure(self, compatibility_args)
        return one_render_response(tool_name, result)

    def _v2_write_guard(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        guarded = self._authorize_write_tool(tool_name, arguments)
        if guarded is None:
            return None
        return one_render_response(tool_name, guarded)

    @staticmethod
    def _closed_arguments(
        arguments: Mapping[str, Any],
        allowed: frozenset[str],
        *,
        prefix: str = "tool arguments",
    ) -> None:
        unknown = sorted(set(arguments) - allowed)
        if unknown:
            raise ValueError(f"{prefix} contains unsupported fields: {', '.join(unknown)}")


__all__ = ["McpRenderV2Mixin"]
