import json
from pathlib import Path

import pytest

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
    assert inventory["distribution_policy"]["repository_publication_approved"] is True
    assert inventory["distribution_policy"]["repository_publication_approval_evidence"] == [
        "https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221"
    ]
    assert any(item["area"] == "mcp_protocol_surface" for item in inventory["public_core_candidates"])
    assert any(item["area"] == "internal_style_packs" for item in inventory["private_or_internal_components"])
    assert inventory["distribution_policy"]["current_status"] == "public_package_approved"


def test_public_core_status_reports_current_gate_consistently():
    status = public_core_status(HUB_ROOT)

    assert status["inventory_valid"] is True
    assert status["package_distribution_allowed"] is True
    assert status["pypi_upload_allowed"] is True
    assert status["repository_public_release_technically_eligible"] is status["release_gate"]["ok"]
    assert status["repository_public_release_authorized"] is True
    assert status["repository_public_release_allowed"] is (
        status["repository_public_release_authorized"]
        and status["repository_public_release_technically_eligible"]
    )
    assert "blockers_by_family" not in status["release_gate"]
    if status["release_gate"]["ok"]:
        assert status["release_gate"]["blocker_families"] == []
        assert status["release_gate"]["next_actions"] == []
        assert status["release_gate"]["action_summary"]["auto_fixable_blocker_count"] == 0
        assert status["release_gate"]["action_summary"]["requires_confirmation"] is False
    else:
        assert status["release_gate"]["blocker_families"]
        assert status["release_gate"]["next_actions"]
        assert status["release_gate"]["action_summary"]["requires_confirmation"] is True


def test_public_core_status_can_include_grouped_release_blockers():
    status = build_public_core_status(HUB_ROOT, include_blockers=True)

    blockers = status["release_gate"]["blockers_by_family"]
    if status["release_gate"]["ok"]:
        assert blockers == {}
    else:
        assert blockers
        assert set(blockers) == set(status["release_gate"]["blocker_families"])


def test_release_blocker_summary_matches_current_gate_state():
    grouped = release_blocker_summary(HUB_ROOT)
    status = public_core_status(HUB_ROOT)

    if status["release_gate"]["ok"]:
        assert grouped == {}
    else:
        assert grouped
        assert set(grouped) == set(status["release_gate"]["blocker_families"])


def test_release_next_actions_group_counts_and_decision_statuses():
    actions = release_next_actions(
        (
            "Private marker 'internal_sample' found in README.md.",
            "Private workflow document path present: docs/internal/protocols/01.md.",
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
        "repository_public_release_technically_eligible": True,
        "repository_public_release_authorized": False,
        "repository_publication_authorization_evidence": [],
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
    assert "- Repository technically eligible for public release: yes" in markdown
    assert "- Repository publication authorized: no" in markdown
    assert "- Repository release allowed: no" in markdown
    assert "- Authorization evidence references: 0" in markdown
    assert "- Technical release gate: blocked" in markdown
    assert "- Auto-fixable technical blockers: 0" in markdown
    assert "does not authorize publication, merge, tagging, or release" in markdown
    assert "authoritative inventory approval fields" in markdown
    assert "Decision record: [public-release-decision-record.md]" in markdown
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


def test_public_release_status_snapshot_is_valid_markdown_report():
    snapshot_path = HUB_ROOT / "docs" / "packaging" / "public-release-status.md"
    snapshot = snapshot_path.read_text(encoding="utf-8")

    assert snapshot.startswith("# FigOps Public Release Status\n")
    assert "- Inventory valid:" in snapshot
    assert "- Package distribution allowed:" in snapshot
    assert "- Repository technically eligible for public release:" in snapshot
    assert "- Repository publication authorized:" in snapshot
    assert "- Repository release allowed:" in snapshot
    assert "- Technical release gate:" in snapshot
    assert "Decision record: [public-release-decision-record.md]" in snapshot
    assert "## Technical Gate Next Actions" in snapshot
    assert "| Family | Count | Status | Confirmation | Action |" in snapshot


def test_public_release_status_snapshot_matches_current_generated_report():
    snapshot_path = HUB_ROOT / "docs" / "packaging" / "public-release-status.md"
    snapshot = snapshot_path.read_text(encoding="utf-8")

    expected = format_public_core_payload(build_public_core_status(HUB_ROOT), "markdown")

    assert snapshot == expected


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


def test_public_core_status_keeps_owner_authorization_when_policy_blocks_technical_eligibility(tmp_path: Path):
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
    assert status["repository_public_release_technically_eligible"] is False
    assert status["repository_public_release_authorized"] is True
    assert status["repository_public_release_allowed"] is False
    assert status["release_gate"]["blocker_count"] == 0
    assert status["pypi_upload_allowed"] is False


def test_public_core_inventory_validation_fails_closed_for_missing_policy():
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory.pop("distribution_policy")

    errors = validate_public_core_inventory(inventory)

    assert any("distribution_policy" in error for error in errors)


def test_public_core_inventory_validation_requires_explicit_repository_authorization():
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory["distribution_policy"].pop("repository_publication_approved")

    errors = validate_public_core_inventory(inventory)

    assert "distribution_policy.repository_publication_approved must be boolean." in errors


def test_public_core_inventory_rejects_repository_approval_without_evidence():
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory["distribution_policy"]["repository_publication_approved"] = True
    inventory["distribution_policy"]["repository_publication_approval_evidence"] = []

    errors = validate_public_core_inventory(inventory)

    assert "repository publication approval requires at least one evidence link." in errors


@pytest.mark.parametrize(
    "reference",
    ["", "approved-by-owner", "http://example.test/approval/1", "https://user:secret@example.test/approval"],
)
def test_public_core_inventory_rejects_unapproved_or_malformed_evidence_reference(reference: str):
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory["distribution_policy"]["repository_publication_approval_evidence"] = [reference]

    errors = validate_public_core_inventory(inventory)

    assert any("must contain only valid HTTPS links" in error for error in errors)


def test_public_core_status_authorizes_only_with_valid_https_evidence(tmp_path: Path):
    inventory = load_public_core_inventory(HUB_ROOT)
    policy = inventory["distribution_policy"]
    policy["repository_publication_approved"] = True
    policy["repository_publication_approval_evidence"] = ["https://approvals.example.test/releases/figops-1"]
    inventory_path = tmp_path / "docs" / "packaging" / "public-core-inventory.json"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Apache-2.0 package distribution.\n", encoding="utf-8")

    status = build_public_core_status(tmp_path)
    markdown = format_public_core_status_markdown(status)

    assert status["repository_public_release_technically_eligible"] is True
    assert status["repository_public_release_authorized"] is True
    assert status["repository_public_release_allowed"] is True
    assert status["repository_publication_authorization_evidence"] == [
        "https://approvals.example.test/releases/figops-1"
    ]
    assert "- Repository publication authorized: yes" in markdown
    assert "- Repository release allowed: yes" in markdown
    assert "- Authorization evidence references: 1" in markdown
    assert "authorization is recorded in the authoritative inventory" in markdown
    assert "authorization remains pending" not in markdown


def test_public_core_status_separates_recorded_authorization_from_a_failed_technical_gate(tmp_path: Path):
    inventory = load_public_core_inventory(HUB_ROOT)
    inventory_path = tmp_path / "docs" / "packaging" / "public-core-inventory.json"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    status = build_public_core_status(tmp_path)
    markdown = format_public_core_status_markdown(status)

    assert status["release_gate"]["ok"] is False
    assert status["repository_public_release_technically_eligible"] is False
    assert status["repository_public_release_authorized"] is True
    assert status["repository_public_release_allowed"] is False
    assert "- Repository publication authorized: yes" in markdown
    assert "- Repository release allowed: no" in markdown


@pytest.mark.parametrize(
    ("approved", "evidence"),
    [
        (False, ["https://approvals.example.test/releases/figops-1"]),
        (True, []),
        (True, ["http://approvals.example.test/releases/figops-1"]),
    ],
)
def test_public_core_status_rejects_missing_or_invalid_authorization_inputs(
    tmp_path: Path, approved: bool, evidence: list[str]
):
    inventory = load_public_core_inventory(HUB_ROOT)
    policy = inventory["distribution_policy"]
    policy["repository_publication_approved"] = approved
    policy["repository_publication_approval_evidence"] = evidence
    inventory_path = tmp_path / "docs" / "packaging" / "public-core-inventory.json"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Apache-2.0 package distribution.\n", encoding="utf-8")

    status = build_public_core_status(tmp_path)

    assert status["repository_public_release_authorized"] is False
    assert status["repository_public_release_allowed"] is False


def test_public_core_inventory_is_json_serializable():
    inventory = load_public_core_inventory(HUB_ROOT)

    assert json.loads(json.dumps(inventory, ensure_ascii=False)) == inventory


def test_public_core_inventory_does_not_embed_private_marker_literals():
    inventory = load_public_core_inventory(HUB_ROOT)
    serialized = json.dumps(inventory, ensure_ascii=False)

    assert not any(marker in serialized for marker in PRIVATE_MARKERS)


def test_public_release_decision_docs_do_not_embed_private_marker_literals():
    doc_paths = (
        HUB_ROOT / "docs" / "packaging" / "public-release-decision-record.md",
        HUB_ROOT / "docs" / "packaging" / "public-release-status.md",
    )

    for doc_path in doc_paths:
        text = doc_path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in PRIVATE_MARKERS)


def test_blocker_family_classification():
    assert blocker_family("LICENSE is proprietary/all-rights-reserved; public release is blocked.") == "license"
    assert blocker_family("Internal/private style packs are present: surfur_internal.") == "style_pack"
    assert blocker_family("Private marker 'internal_sample' found in README.md.") == "private_marker"
    assert (
        blocker_family("Private workflow document path present: docs/internal/protocols/01.md.")
        == "private_workflow_doc"
    )
