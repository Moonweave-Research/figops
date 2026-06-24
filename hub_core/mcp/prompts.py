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
            target_format = self._prompt_quote(arguments.get("target_format", "nature"))
            plot_type = self._prompt_quote(arguments.get("plot_type", "scatter"))
            text = (
                "Render a publication-style FigOps figure from structured CSV data.\n"
                f"- data_path: {data_path}\n"
                f"- x_column: {x_column}\n"
                f"- y_column: {y_column}\n"
                f"- target_format: {target_format}\n"
                f"- plot_type: {plot_type}\n\n"
                "Workflow:\n"
                "1. If style support is uncertain, call figops.list_styles.\n"
                "2. Call figops.render_csv_graph with dry_run=true using the supplied CSV and columns.\n"
                "3. Inspect calculation_checks, visual_preflight_status, failure_stage, and resolution_hint.\n"
                "4. Rerun figops.render_csv_graph without dry_run only when the dry run is clean "
                "or the user accepts warnings.\n"
                "5. Call figops.collect_artifacts for the returned job_id.\n"
                "6. If manual_review_needed=true, do not claim publication readiness without manual review."
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
                "Workflow:\n"
                "1. Call figops.inspect_project for the selected project.\n"
                "2. Call figops.validate_project for the same selector.\n"
                "3. Inspect config_errors, data_contract_errors, style_errors, missing_inputs, missing_outputs, "
                "and normalization_needed.\n"
                "4. Avoid rendering or normalization unless the user explicitly asks."
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
                "Workflow:\n"
                "1. Call figops.inspect_project.\n"
                "2. Call figops.normalize_project_structure with dry_run=true.\n"
                "3. Show the manifest and preserve project style choices.\n"
                "4. Apply only after user approval.\n"
                "5. Call figops.validate_project after apply."
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
            text = (
                "Project figure workflow:\n"
                "1. Call figops.inspect_project for the selected project.\n"
                "2. Call figops.validate_project and stop on status=error.\n"
                f"3. Call figops.render_project_figure for selector {selector!r} with dry_run=true first.\n"
                "4. If dry_run is clean, call figops.render_project_figure without dry_run.\n"
                "5. Call figops.collect_artifacts for the returned job_id.\n"
                "6. Report manifest_path, status_path, provenance, failure_stage, resolution_hint, "
                "and manual_review_needed."
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
