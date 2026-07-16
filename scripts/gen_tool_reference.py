from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DOC = ROOT / "docs" / "tools.md"
PROFILE_TOOL_DOCS = {
    "v2": ROOT / "docs" / "tools-v2.md",
    "compatibility": ROOT / "docs" / "tools-compatibility.md",
}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_public_release import PRIVATE_MARKERS  # noqa: E402

PUBLIC_REFERENCE_REDACTIONS = (
    "private_project_root",
    "private_control_project",
    "private_measurement_folder",
    "internal_style_format",
    "internal_style_profile",
)


def _json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(_redact_public_reference_payload(payload), indent=2, sort_keys=True) + "\n```"


def _redact_public_reference_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: _redact_public_reference_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_redact_public_reference_payload(value) for value in payload]
    if isinstance(payload, str):
        redacted = payload
        for index, marker in enumerate(PRIVATE_MARKERS):
            replacement = (
                PUBLIC_REFERENCE_REDACTIONS[index] if index < len(PUBLIC_REFERENCE_REDACTIONS) else "private_marker"
            )
            redacted = redacted.replace(marker, replacement)
        return redacted
    return payload


def render_tool_reference(profile: str | None = None) -> str:
    from hub_core.mcp.schemas import describe_figops_surface, list_tool_definitions

    if profile is None:
        surface = describe_figops_surface()
        tools = surface["tools"]
    else:
        definitions = list_tool_definitions(profile=profile, write_tools_enabled=True)
        tools = [
            {
                "name": tool["name"],
                "purpose": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            }
            for tool in definitions
            if profile != "compatibility" or tool["name"].startswith("figops.")
        ]
        surface = {"plot_types": [], "semantic_checks": []}
    title_suffix = "" if profile is None else f" — {profile} profile"
    profile_flag = "" if profile is None else f" --profile {profile}"
    lines = [
        f"# FigOps MCP Tool Reference{title_suffix}",
        "",
        "This file is generated from the live FigOps MCP registries.",
        "Regenerate it with:",
        "",
        "```bash",
        f"python hub_uv.py run python scripts/gen_tool_reference.py --write{profile_flag}",
        "```",
        "",
        "The freshness test fails if this committed file drifts from the registry output.",
        "",
        "## Tools",
        "",
    ]

    for tool in tools:
        lines.extend(
            [
                f"### `{tool['name']}`",
                "",
                tool["purpose"],
                "",
                "**Input schema**",
                "",
                _json_block(tool["inputSchema"]),
                "",
                "**Output schema**",
                "",
                _json_block(tool["outputSchema"]),
                "",
            ]
        )

    if profile == "compatibility":
        lines.extend(["## Frozen `graphhub.*` aliases", ""])
        for definition in definitions:
            name = definition["name"]
            if name.startswith("graphhub."):
                lines.append(f"- `{name}` → `{name.replace('graphhub.', 'figops.', 1)}`")
        lines.append("")

    lines.extend(["## Plot Types", ""])
    for plot_type in surface["plot_types"]:
        lines.extend(
            [
                f"### `{plot_type['name']}`",
                "",
                "**Capabilities**",
                "",
                _json_block(plot_type["capabilities"]),
                "",
                "**Argument schema**",
                "",
                _json_block(plot_type["arg_schema"]),
                "",
                "**Worked example**",
                "",
                _json_block(plot_type["worked_example"]),
                "",
            ]
        )

    lines.extend(["## Semantic Checks", ""])
    for check in surface["semantic_checks"]:
        lines.extend(
            [
                f"### `{check['name']}`",
                "",
                check["purpose"],
                "",
                "**Schema**",
                "",
                _json_block(check["schema"]),
                "",
                "**Example**",
                "",
                _json_block(check["example"]),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/tools.md from live MCP registries")
    parser.add_argument("--write", action="store_true", help="Write docs/tools.md")
    parser.add_argument("--check", action="store_true", help="Fail if docs/tools.md is stale")
    parser.add_argument("--profile", choices=("v2", "compatibility"), help="Generate one surface profile reference")
    args = parser.parse_args()

    rendered = render_tool_reference(args.profile)
    output_path = PROFILE_TOOL_DOCS.get(args.profile, TOOLS_DOC)
    if args.write:
        # Generated-reference byte metrics are release witnesses. Keep their
        # on-disk representation independent of the host checkout's newline
        # policy (notably Windows CRLF versus macOS/Linux LF).
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
        return 0
    if args.check:
        current = output_path.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit(f"{output_path.relative_to(ROOT)} is stale; regenerate the selected profile.")
        return 0
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
