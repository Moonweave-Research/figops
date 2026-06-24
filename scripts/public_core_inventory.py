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
        if policy.get("current_status") != "private_internal":
            errors.append("distribution_policy.current_status must remain private_internal until relicensing.")
        if policy.get("public_pypi_allowed") is not False:
            errors.append("distribution_policy.public_pypi_allowed must be false until the public release gate passes.")
        if not policy.get("license_decision_required"):
            errors.append("distribution_policy.license_decision_required must be true.")

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


def public_core_status(root: Path = REPO_ROOT) -> dict[str, Any]:
    inventory = load_public_core_inventory(root)
    inventory_errors = validate_public_core_inventory(inventory)
    release_result = run_release_check(root)
    families = sorted({blocker_family(blocker) for blocker in release_result.blockers})
    policy = inventory.get("distribution_policy", {})
    pypi_upload_allowed = (
        not inventory_errors
        and release_result.ok
        and isinstance(policy, dict)
        and policy.get("public_pypi_allowed") is True
    )
    return {
        "schema_version": inventory.get("schema_version"),
        "inventory_path": str((root / INVENTORY_RELATIVE_PATH).resolve()),
        "inventory_valid": not inventory_errors,
        "inventory_errors": inventory_errors,
        "distribution_policy": policy,
        "release_gate": {
            "ok": release_result.ok,
            "blocker_count": len(release_result.blockers),
            "blocker_families": families,
        },
        "pypi_upload_allowed": pypi_upload_allowed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root to inspect")
    parser.add_argument("--status", action="store_true", help="Emit current release status plus inventory validity")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    payload = public_core_status(root) if args.status else load_public_core_inventory(root)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.status:
        return 0 if payload["inventory_valid"] else 1
    errors = validate_public_core_inventory(payload)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
