"""Command-line report for journal style provenance metadata."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from .journal_specs import list_preflight_tokens, list_supported_preflight_targets


def build_style_report(target_format: str) -> dict[str, object]:
    """Return machine-readable provenance metadata for a target format."""
    return {
        "target_format": target_format,
        "tokens": list_preflight_tokens(target_format),
    }


def format_style_report(report: dict[str, object]) -> str:
    """Format a provenance report for human CLI output."""
    lines = [f"target_format: {report['target_format']}"]
    for token in report["tokens"]:
        lines.append("")
        lines.append(f"{report['target_format']}.{token['key']} = {token['value']}")
        lines.append(f"  provenance: {token['provenance']}")
        lines.append(f"  enforcement: {token['enforcement']}")
        lines.append(f"  source: {token['source_url'] or 'internal'}")
        lines.append(f"  note: {token['source_note']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report journal style provenance metadata.")
    parser.add_argument("--target-format", default="nature", help="Target format to report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List target formats with preflight provenance metadata and exit.",
    )
    args = parser.parse_args(argv)

    if args.list_targets:
        targets = list_supported_preflight_targets()
        print(json.dumps(targets, indent=2) if args.json else "\n".join(targets))
        return 0

    report = build_style_report(args.target_format)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else format_style_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
