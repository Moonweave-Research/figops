#!/usr/bin/env python3
"""Report large Python modules for architecture maintenance docs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = ("hub_core", "plotting", "themes")


def architecture_inventory(
    root: Path = REPO_ROOT,
    *,
    roots: Sequence[str] = DEFAULT_ROOTS,
    min_lines: int = 800,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_root in roots:
        source_path = root / source_root
        if not source_path.is_dir():
            raise FileNotFoundError(f"Architecture inventory root not found: {source_path}")
        for path in source_path.rglob("*.py"):
            line_count = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
            if line_count > min_lines:
                rows.append({"file": path.relative_to(root).as_posix(), "lines": line_count})
    return sorted(rows, key=lambda row: (-int(row["lines"]), str(row["file"])))


def render_architecture_inventory_markdown(rows: Sequence[dict[str, Any]]) -> str:
    lines = ["| File | Lines |", "|---|---:|"]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['lines']} |")
    return "\n".join(lines)


def render_architecture_inventory_text(rows: Sequence[dict[str, Any]]) -> str:
    return "\n".join(f"{int(row['lines']):5d}  {row['file']}" for row in rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-lines", type=int, default=800)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--roots", nargs="+", default=list(DEFAULT_ROOTS))
    parser.add_argument("--format", choices=("markdown", "text", "json"), default="markdown")
    args = parser.parse_args(argv)

    rows = architecture_inventory(args.root, roots=args.roots, min_lines=args.min_lines)
    if args.format == "json":
        print(json.dumps(rows, indent=2, sort_keys=True))
    elif args.format == "text":
        print(render_architecture_inventory_text(rows))
    else:
        print(render_architecture_inventory_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
