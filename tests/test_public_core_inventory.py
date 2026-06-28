import json
from pathlib import Path

from scripts.check_public_release import PRIVATE_MARKERS
from scripts.public_core_inventory import (
    blocker_family,
    build_public_core_status,
    format_public_core_payload,
    format_public_core_status_markdown,
    load_public_core_inventory,
    main,
    public_core_status,
    release_action_summary,
    release_blocker_summary,
    release_next_actions,
    validate_public_core_inventory,
)

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_public_core_inventory_schema_is_valid():
    inventory = load_public_core_inventory(HUB_ROOT)

    assert validate_public_core_inventory(inventory) == []
    assert inventory["distribution_policy"]["public_pypi_allowed"] is True
    assert inventory["distribution_policy"]["license_decision_required"] is False
    assert any(item["area"] == "mcp_protocol_surface" for item in inventory["public_core_candidates"])
    assert any(item["area"] == "internal_style_packs" for item in inventory["private_or_internal_components"])
    assert inventory["distribution_policy"]["current_status"] == "public_package_approved"


def test_public_core_status_reports_current_gate_as_blocked():
    status = public_core_status(HUB_ROOT)

    assert status["inventory_valid"] is True
    assert status["release_gate"]["ok"] is False
    assert status["package_distribution_allowed"] is True
    assert status["repository_public_release_allowed"] is False
    assert status["pypi_upload_allowed"] is True
    assert "private_marker" in status["release_gate"]["blocker_families"]
    assert "style_pack" in status["release_gate"]["blocker_families"]
    next_actions = {action["family"]: action for action in status["release_gate"]["next_actions"]}
    assert next_actions["private_marker"]["requires_confirmation"] is True
    assert next_actions["post_tag_metadata"]["status"] == "requires_release_decision"
    assert status["release_gate"]["action_summary"]["auto_fixable_blocker_count"] == 0
    assert status["release_gate"]["action_summary"]["requires_confirmation"] is True
    assert "blockers_by_family" not in status["release_gate"]


def test_public_core_status_can_include_grouped_release_blockers():
    status = build_public_core_status(HUB_ROOT, include_blockers=True)

    blockers = status["release_gate"]["blockers_by_family"]
    assert "private_marker" in blockers
    assert "style_pack" in blockers
    assert any("Private marker" in blocker for blocker in blockers["private_marker"])


def test_release_blocker_summary_groups_by_family():
    grouped = release_blocker_summary(HUB_ROOT)

    assert "private_marker" in grouped
    assert "private_workflow_doc" in grouped
    assert all(isinstance(blocker, str) for blocker in grouped["private_marker"])


def test_release_next_actions_group_counts_and_decision_statuses():
    actions = release_next_actions(
        (
            "Private marker 'internal_sample' found in README.md.",
            "Private workflow document path present: docs/hks/01.md.",
            "Unable to decode UTF-8 text file: bad.txt (invalid start byte at byte 1).",
        )
    )

    by_family = {action["family"]: action for action in actions}
    assert by_family["private_marker"]["count"] == 1
    assert by_family["private_marker"]["status"] == "requires_decision"
    assert by_family["private_workflow_doc"]["requires_confirmation"] is True
    assert by_family["encoding"]["status"] == "can_fix"
    assert by_family["encoding"]["requires_confirmation"] is False


def test_release_action_summary_counts_auto_fixable_and_decision_blockers():
    summary = release_action_summary(
        [
            {
                "family": "encoding",
                "count": 2,
                "status": "can_fix",
                "action": "Convert to UTF-8.",
                "requires_confirmation": False,
            },
            {
                "family": "private_marker",
                "count": 3,
                "status": "requires_decision",
                "action": "Sanitize or relocate.",
                "requires_confirmation": True,
            },
        ]
    )

    assert summary["auto_fixable_blocker_count"] == 2
    assert summary["requires_confirmation_blocker_count"] == 3
    assert summary["requires_confirmation"] is True


def test_format_public_core_status_markdown_summarizes_decision_state():
    payload = {
        "inventory_valid": True,
        "package_distribution_allowed": True,
        "repository_public_release_allowed": False,
        "release_gate": {
            "ok": False,
            "blocker_count": 3,
            "action_summary": {
                "auto_fixable_blocker_count": 0,
                "requires_confirmation_blocker_count": 3,
                "requires_confirmation": True,
            },
            "next_actions": [
                {
                    "family": "private_marker",
                    "count": 3,
                    "status": "requires_decision",
                    "action": "Sanitize or relocate.",
                    "requires_confirmation": True,
                }
            ],
        },
    }

    markdown = format_public_core_status_markdown(payload)

    assert "# FigOps Public Release Status" in markdown
    assert "- Package distribution allowed: yes" in markdown
    assert "- Repository public release allowed: no" in markdown
    assert "- Auto-fixable blockers: 0" in markdown
    assert "| private_marker | 3 | requires_decision | yes | Sanitize or relocate. |" in markdown


def test_format_public_core_payload_keeps_json_as_default():
    rendered = format_public_core_payload({"ok": True}, "json")

    assert rendered.endswith("\n")
    assert json.loads(rendered) == {"ok": True}


def test_public_core_inventory_markdown_cli_requires_status(capsys):
    exit_code = main(["--status", "--format", "markdown"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "# FigOps Public Release Status" in captured.out
    assert "```" not in captured.out


def test_public_core_inventory_output_writes_markdown_report(tmp_path: Path, capsys):
    report_path = tmp_path / "reports" / "public-release-status.md"

    exit_code = main(["--status", "--format", "markdown", "--output", str(report_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""
    assert "# FigOps Public Release Status" in report_path.read_text(encoding="utf-8")


def test_public_core_inventory_output_writes_json_report(tmp_path: Path, capsys):
    report_path = tmp_path / "reports" / "public-release-status.json"

    exit_code = main(["--status", "--output", str(report_path)])

    captured = capsys.readouterr()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert captured.out == ""
    assert payload["schema_version"] == "public_core_inventory/1"


def test_public_core_status_requires_approved_current_status_for_pypi_allowed(tmp_path: Path):
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory["distribution_policy"]["current_status"] = "private_internal"
    inventory_path = tmp_path / "docs" / "packaging" / "public-core-inventory.json"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Apache-2.0 package distribution.\n", encoding="utf-8")

    status = build_public_core_status(tmp_path)

    assert status["inventory_valid"] is True
    assert status["package_distribution_allowed"] is False
    assert status["repository_public_release_allowed"] is False
    assert status["release_gate"]["blocker_count"] > 0
    assert status["pypi_upload_allowed"] is False


def test_public_core_inventory_validation_fails_closed_for_missing_policy():
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory.pop("distribution_policy")

    errors = validate_public_core_inventory(inventory)

    assert any("distribution_policy" in error for error in errors)


def test_public_core_inventory_is_json_serializable():
    inventory = load_public_core_inventory(HUB_ROOT)

    assert json.loads(json.dumps(inventory, ensure_ascii=False)) == inventory


def test_public_core_inventory_does_not_embed_private_marker_literals():
    inventory = load_public_core_inventory(HUB_ROOT)
    serialized = json.dumps(inventory, ensure_ascii=False)

    assert not any(marker in serialized for marker in PRIVATE_MARKERS)


def test_blocker_family_classification():
    assert blocker_family("LICENSE is proprietary/all-rights-reserved; public release is blocked.") == "license"
    assert blocker_family("Internal/private style packs are present: surfur_internal.") == "style_pack"
    assert blocker_family("Private marker 'internal_sample' found in README.md.") == "private_marker"
    assert blocker_family("Private workflow document path present: docs/hks/01.md.") == "private_workflow_doc"
