#!/usr/bin/env python3
"""Report the public-core candidate inventory and current release blockers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_RELATIVE_PATH = Path("docs/packaging/public-core-inventory.json")
REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "distribution_policy",
    "public_core_candidates",
    "private_or_internal_components",
    "release_exit_criteria",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_public_release import run_release_check  # noqa: E402


def load_public_core_inventory(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = root / INVENTORY_RELATIVE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def validate_public_core_inventory(inventory: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(inventory))
    if missing:
        errors.append(f"Missing top-level inventory keys: {missing}")
    if inventory.get("schema_version") != "public_core_inventory/1":
        errors.append("schema_version must be 'public_core_inventory/1'.")

    policy = inventory.get("distribution_policy")
    if not isinstance(policy, dict):
        errors.append("distribution_policy must be an object.")
    else:
        if policy.get("current_status") not in {"private_internal", "public_package_approved", "public_pypi_approved"}:
            errors.append("distribution_policy.current_status must be a known release state.")
        if not isinstance(policy.get("public_pypi_allowed"), bool):
            errors.append("distribution_policy.public_pypi_allowed must be boolean.")
        if not isinstance(policy.get("license_decision_required"), bool):
            errors.append("distribution_policy.license_decision_required must be boolean.")
        if policy.get("public_pypi_allowed") and policy.get("license_decision_required"):
            errors.append("distribution_policy cannot allow PyPI while license_decision_required is true.")

    for key in ("public_core_candidates", "private_or_internal_components", "release_exit_criteria"):
        value = inventory.get(key)
        if not isinstance(value, list) or not value:
            errors.append(f"{key} must be a non-empty list.")

    return errors


def blocker_family(blocker: str) -> str:
    if blocker.startswith("LICENSE") or blocker.startswith("NOTICE"):
        return "license"
    if "Internal/private style packs" in blocker or blocker.startswith("Style pack"):
        return "style_pack"
    if blocker.startswith("Private marker"):
        return "private_marker"
    if blocker.startswith("Private workflow document"):
        return "private_workflow_doc"
    if "Release metadata is stale" in blocker:
        return "post_tag_metadata"
    if blocker.startswith("Unable to decode"):
        return "encoding"
    return "other"


BLOCKER_ACTIONS: dict[str, dict[str, object]] = {
    "license": {
        "status": "requires_decision",
        "action": "Record license clearance and update LICENSE/NOTICE only after approval.",
        "requires_confirmation": True,
    },
    "style_pack": {
        "status": "requires_decision",
        "action": "Split or remove internal style packs from the public repository candidate.",
        "requires_confirmation": True,
    },
    "private_marker": {
        "status": "requires_decision",
        "action": "Sanitize or relocate files that contain real project identifiers or private style names.",
        "requires_confirmation": True,
    },
    "private_workflow_doc": {
        "status": "requires_decision",
        "action": "Move internal workflow documents out of the public repository candidate.",
        "requires_confirmation": True,
    },
    "post_tag_metadata": {
        "status": "requires_release_decision",
        "action": "Choose the next release version, then bump pyproject and changelog together.",
        "requires_confirmation": True,
    },
    "encoding": {
        "status": "can_fix",
        "action": "Convert undecodable tracked text files to UTF-8 or remove them from the candidate.",
        "requires_confirmation": False,
    },
    "other": {
        "status": "inspect",
        "action": "Inspect unclassified blockers and add a specific action mapping when understood.",
        "requires_confirmation": True,
    },
}


def release_next_actions(blockers: tuple[str, ...]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for blocker in blockers:
        family = blocker_family(blocker)
        counts[family] = counts.get(family, 0) + 1

    actions: list[dict[str, object]] = []
    for family in sorted(counts):
        action = BLOCKER_ACTIONS.get(family, BLOCKER_ACTIONS["other"])
        actions.append(
            {
                "family": family,
                "count": counts[family],
                "status": action["status"],
                "action": action["action"],
                "requires_confirmation": action["requires_confirmation"],
            }
        )
    return actions


def release_action_summary(actions: list[dict[str, object]]) -> dict[str, object]:
    auto_fixable = 0
    requires_confirmation = 0
    for action in actions:
        count = int(action["count"])
        if action["requires_confirmation"]:
            requires_confirmation += count
        else:
            auto_fixable += count
    return {
        "auto_fixable_blocker_count": auto_fixable,
        "requires_confirmation_blocker_count": requires_confirmation,
        "requires_confirmation": requires_confirmation > 0,
    }


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def format_public_core_status_markdown(payload: dict[str, Any]) -> str:
    release_gate = payload["release_gate"]
    action_summary = release_gate["action_summary"]
    lines = [
        "# FigOps Public Release Status",
        "",
        f"- Inventory valid: {_yes_no(payload['inventory_valid'])}",
        f"- Package distribution allowed: {_yes_no(payload['package_distribution_allowed'])}",
        f"- Repository public release allowed: {_yes_no(payload['repository_public_release_allowed'])}",
        f"- Release gate: {'ok' if release_gate['ok'] else 'blocked'}",
        f"- Total blockers: {release_gate['blocker_count']}",
        f"- Auto-fixable blockers: {action_summary['auto_fixable_blocker_count']}",
        f"- Confirmation-required blockers: {action_summary['requires_confirmation_blocker_count']}",
        "",
        "## Next Actions",
        "",
        "| Family | Count | Status | Confirmation | Action |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for action in release_gate["next_actions"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(action["family"]),
                    _markdown_cell(action["count"]),
                    _markdown_cell(action["status"]),
                    _yes_no(action["requires_confirmation"]),
                    _markdown_cell(action["action"]),
                ]
            )
            + " |"
        )
    if "blockers_by_family" in release_gate:
        lines.extend(["", "## Blocker Details", ""])
        for family, blockers in release_gate["blockers_by_family"].items():
            lines.append(f"### {family}")
            for blocker in blockers:
                lines.append(f"- {_markdown_cell(blocker)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def public_core_status(root: Path = REPO_ROOT) -> dict[str, Any]:
    return build_public_core_status(root)


def release_blocker_summary(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    release_result = run_release_check(root)
    grouped: dict[str, list[str]] = {}
    for blocker in release_result.blockers:
        grouped.setdefault(blocker_family(blocker), []).append(blocker)
    return {family: sorted(blockers) for family, blockers in sorted(grouped.items())}


def build_public_core_status(root: Path = REPO_ROOT, *, include_blockers: bool = False) -> dict[str, Any]:
    inventory = load_public_core_inventory(root)
    inventory_errors = validate_public_core_inventory(inventory)
    release_result = run_release_check(root)
    families = sorted({blocker_family(blocker) for blocker in release_result.blockers})
    policy = inventory.get("distribution_policy", {})
    package_distribution_allowed = (
        not inventory_errors
        and isinstance(policy, dict)
        and policy.get("public_pypi_allowed") is True
        and policy.get("license_decision_required") is False
        and policy.get("current_status") in {"public_package_approved", "public_pypi_approved"}
    )
    next_actions = release_next_actions(release_result.blockers)
    payload = {
        "schema_version": inventory.get("schema_version"),
        "inventory_path": str((root / INVENTORY_RELATIVE_PATH).resolve()),
        "inventory_valid": not inventory_errors,
        "inventory_errors": inventory_errors,
        "distribution_policy": policy,
        "release_gate": {
            "ok": release_result.ok,
            "blocker_count": len(release_result.blockers),
            "blocker_families": families,
            "action_summary": release_action_summary(next_actions),
            "next_actions": next_actions,
        },
        "package_distribution_allowed": package_distribution_allowed,
        "repository_public_release_allowed": release_result.ok,
        "pypi_upload_allowed": package_distribution_allowed,
    }
    if include_blockers:
        payload["release_gate"]["blockers_by_family"] = release_blocker_summary(root)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root to inspect")
    parser.add_argument("--status", action="store_true", help="Emit current release status plus inventory validity")
    parser.add_argument(
        "--include-blockers",
        action="store_true",
        help="When used with --status, include sorted release blockers grouped by blocker family",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format. Markdown is available for --status decision reports.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if args.format == "markdown" and not args.status:
        parser.error("--format markdown requires --status")
    payload = (
        build_public_core_status(root, include_blockers=args.include_blockers)
        if args.status
        else load_public_core_inventory(root)
    )
    if args.format == "markdown":
        print(format_public_core_status_markdown(payload), end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.status:
        return 0 if payload["inventory_valid"] else 1
    errors = validate_public_core_inventory(payload)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
