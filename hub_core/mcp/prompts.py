from __future__ import annotations

import json
from typing import Any


class McpPromptsMixin:
    """FigOps MCP prompt handlers."""

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        if name == "make_publication_graph_from_csv":
            self._validate_prompt_arguments(
                name,
                arguments,
                required={"data_path", "x_column", "y_column"},
                optional={"target_format", "plot_type"},
            )
            data_path = self._prompt_quote(arguments["data_path"])
            x_column = self._prompt_quote(arguments["x_column"])
            y_column = self._prompt_quote(arguments["y_column"])
            effective_style = arguments.get("target_format", "neutral" if self.surface_profile == "v2" else "nature")
            target_format = self._prompt_quote(effective_style)
            plot_type = self._prompt_quote(arguments.get("plot_type", "scatter"))
            v2 = self.surface_profile == "v2"
            render_tool = "figops.render_basic_csv" if v2 else "figops.render_csv_graph"
            x_argument = "x" if v2 else "x_column"
            y_argument = "y" if v2 else "y_column"
            style_argument = "style_policy" if v2 else "target_format"
            render_arguments: dict[str, Any] = {
                "data_path": str(arguments["data_path"]),
                x_argument: str(arguments["x_column"]),
                y_argument: str(arguments["y_column"]),
                "plot_type": str(arguments.get("plot_type", "scatter")),
            }
            if "target_format" in arguments or not v2:
                render_arguments[style_argument] = str(effective_style)
            discovery_guidance = (
                "figops.inspect_data is optional when schema facts are uncertain; figops.list_styles is optional "
                "when style support is uncertain."
                if v2
                else "figops.list_styles and figops.collect_artifacts remain optional compatibility views."
            )
            text = (
                "Author and render a FigOps figure from structured CSV data.\n"
                f"- data_path: {data_path}\n"
                f"- {x_argument}: {x_column}\n"
                f"- {y_argument}: {y_column}\n"
                f"- {style_argument}: {target_format}\n"
                f"- plot_type: {plot_type}\n\n"
                "Callable arguments:\n"
                f"{json.dumps(render_arguments, ensure_ascii=False, sort_keys=True)}\n\n"
                f"The columns are known, so {render_tool} can render in one call; no dry-run or collect call is a "
                f"prerequisite. {discovery_guidance} "
                "Inspect the returned evidence and preview URI, use visual judgment, and make revisions "
                "proportional to the observed issue. If manual_review_needed=true, do not claim publication approval."
            )
            return self._prompt_payload(
                "Workflow for rendering a publication-style graph from structured CSV data.",
                text,
            )

        if name == "inspect_graph_project_quality":
            self._validate_prompt_arguments(
                name,
                arguments,
                required=set(),
                optional={"project_id", "project_path"},
            )
            if not arguments.get("project_id") and not arguments.get("project_path"):
                raise ValueError("project_id or project_path is required.")
            selector = (
                f"project_id: {self._prompt_quote(arguments['project_id'])}"
                if arguments.get("project_id")
                else f"project_path: {self._prompt_quote(arguments['project_path'])}"
            )
            text = (
                "Inspect FigOps project quality without executing analysis or plotting scripts.\n"
                f"- {selector}\n\n"
                "On the compact v2 surface, call figops.describe with kind=project_structure and the project "
                "selector. On the compatibility surface, use figops.inspect_project or figops.validate_project "
                "according to the evidence needed. "
                "Inspect config_errors, data_contract_errors, style_errors, missing_inputs, missing_outputs, "
                "normalization_needed, roles, graph, findings, unknowns, and proposed_changes. Avoid rendering "
                "or normalization unless the user asks."
            )
            return self._prompt_payload("Workflow for inspecting graph project quality.", text)

        if name == "standardize_existing_graph_project":
            self._validate_prompt_arguments(
                name,
                arguments,
                required={"project_path"},
                optional={"move_policy"},
            )
            project_path = self._prompt_quote(arguments["project_path"])
            move_policy = self._prompt_quote(arguments.get("move_policy", "copy"))
            text = (
                "Plan safe FigOps project normalization.\n"
                f"- project_path: {project_path}\n"
                f"- move_policy: {move_policy}\n\n"
                "Because normalization mutates source structure, call figops.normalize_project_structure with "
                "dry_run=true, show its manifest, preserve project style choices, and apply only after explicit "
                "user approval. figops.inspect_project and figops.validate_project are optional evidence views."
            )
            return self._prompt_payload("Workflow for planning safe project normalization.", text)

        if name == "render_project_figure":
            self._validate_prompt_arguments(
                name,
                arguments,
                required=set(),
                optional={"project_id", "project_path", "figure_id", "figure_output"},
            )
            if not arguments.get("project_id") and not arguments.get("project_path"):
                raise ValueError("render_project_figure requires project_id or project_path.")
            selector = arguments.get("figure_id") or arguments.get("figure_output") or "<single configured figure>"
            render_tool = (
                "figops.render_project_script" if self.surface_profile == "v2" else "figops.render_project_figure"
            )
            optional_views = (
                "Use figops.describe kind=project_structure only when declared-role or dependency detail is needed."
                if self.surface_profile == "v2"
                else "figops.inspect_project, figops.validate_project, and figops.collect_artifacts are optional "
                "compatibility views."
            )
            text = (
                f"Render configured selector {selector!r} with {render_tool} in one call; a dry run or collect call "
                f"is not a prerequisite. {optional_views} "
                "Inspect returned evidence and preview, then make revisions proportional to observed issues. Preserve "
                "provenance, failure_stage, resolution_hint, and manual_review_needed; never treat automatic QA "
                "as publication approval."
            )
            return self._prompt_payload(
                "Workflow for rendering one configured project figure through FigOps MCP.",
                text,
            )

        raise FileNotFoundError(f"Unknown prompt: {name}")

    @staticmethod
    def _prompt_payload(description: str, text: str) -> dict[str, Any]:
        return {"description": description, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    @staticmethod
    def _prompt_quote(value: Any) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _validate_prompt_arguments(
        name: str,
        arguments: dict[str, Any],
        *,
        required: set[str],
        optional: set[str],
    ) -> None:
        allowed = required | optional
        unknown = sorted(set(arguments) - allowed)
        if unknown:
            raise ValueError(f"Unknown prompt argument(s) for {name}: {', '.join(unknown)}")
        missing = sorted(
            key for key in required if not isinstance(arguments.get(key), str) or not arguments.get(key).strip()
        )
        if missing:
            raise ValueError(f"Missing required prompt argument(s) for {name}: {', '.join(missing)}")
        invalid = sorted(
            key
            for key, value in arguments.items()
            if key in allowed and (not isinstance(value, str) or not value.strip())
        )
        if invalid:
            raise ValueError(f"Prompt argument(s) must be non-empty strings for {name}: {', '.join(invalid)}")
