import json
from pathlib import Path

from scripts.public_core_inventory import (
    blocker_family,
    load_public_core_inventory,
    public_core_status,
    validate_public_core_inventory,
)

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_public_core_inventory_schema_is_valid():
    inventory = load_public_core_inventory(HUB_ROOT)

    assert validate_public_core_inventory(inventory) == []
    assert inventory["distribution_policy"]["public_pypi_allowed"] is False
    assert inventory["distribution_policy"]["license_decision_required"] is True
    assert any(item["area"] == "mcp_protocol_surface" for item in inventory["public_core_candidates"])
    assert any(item["area"] == "internal_style_packs" for item in inventory["private_or_internal_components"])


def test_public_core_status_reports_current_gate_as_blocked():
    status = public_core_status(HUB_ROOT)

    assert status["inventory_valid"] is True
    assert status["release_gate"]["ok"] is False
    assert status["pypi_upload_allowed"] is False
    assert "license" in status["release_gate"]["blocker_families"]
    assert "style_pack" in status["release_gate"]["blocker_families"]


def test_public_core_inventory_validation_fails_closed_for_missing_policy():
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory.pop("distribution_policy")

    errors = validate_public_core_inventory(inventory)

    assert any("distribution_policy" in error for error in errors)


def test_public_core_inventory_is_json_serializable():
    inventory = load_public_core_inventory(HUB_ROOT)

    assert json.loads(json.dumps(inventory, ensure_ascii=False)) == inventory


def test_blocker_family_classification():
    assert blocker_family("LICENSE is proprietary/all-rights-reserved; public release is blocked.") == "license"
    assert blocker_family("Internal/private style packs are present: surfur_internal.") == "style_pack"
    assert blocker_family("Private marker 'PI_control' found in README.md.") == "private_marker"
    assert blocker_family("Private workflow document path present: docs/hks/01.md.") == "private_workflow_doc"
