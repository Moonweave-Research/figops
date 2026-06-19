from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DOC = ROOT / "docs" / "tools.md"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _json_block(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"


def render_tool_reference() -> str:
    from hub_core.mcp.schemas import describe_graphhub_surface

    surface = describe_graphhub_surface()
    lines = [
        "# Graph Hub MCP Tool Reference",
        "",
        "This file is generated from the live Graph Hub MCP registries.",
        "Regenerate it with:",
        "",
        "```bash",
        "uv run python scripts/gen_tool_reference.py --write",
        "```",
        "",
        "The freshness test fails if this committed file drifts from the registry output.",
        "",
        "## Tools",
        "",
    ]

    for tool in surface["tools"]:
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
    args = parser.parse_args()

    rendered = render_tool_reference()
    if args.write:
        TOOLS_DOC.write_text(rendered, encoding="utf-8")
        return 0
    if args.check:
        current = TOOLS_DOC.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit("docs/tools.md is stale; run `uv run python scripts/gen_tool_reference.py --write`.")
        return 0
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
