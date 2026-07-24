from __future__ import annotations

import copy
from copy import deepcopy

from hub_core.approval_authority import (
    ApprovalAuthorityRoot,
    ApprovalRecord,
    canonical_plan_digest,
    verify_approval_authority,
)


def _plan() -> dict:
    plan = {
        "version": "2",
        "project_root_identity": {"device": 1, "inode": 42},
        "config_sha256": "a" * 64,
        "config_identity": {"device": 1, "inode": 99},
        "entries": [{"source": "legacy/a.csv", "destination": "raw/a.csv", "role": "raw"}],
        "approved_mappings": [{"source": "legacy/a.csv", "destination": "raw/a.csv", "role": "raw"}],
        "config_diff": [],
        "hardcoded_unresolved_references": [],
        "unresolved_proposals": [],
    }
    plan["digest"] = canonical_plan_digest(plan)
    return plan


def _issue(root: ApprovalAuthorityRoot, plan: dict, **kwargs):
    options = {
        "reviewer_identity": "principal-investigator:alice",
        "reviewer_role": "principal_investigator",
        "issued_at": "2026-07-24T00:00:00Z",
        "expires_at": "2026-07-25T00:00:00Z",
    }
    options.update(kwargs)
    return root.issue(plan, **options)


def test_approval_is_only_valid_through_the_host_owned_root() -> None:
    plan = _plan()
    root = ApprovalAuthorityRoot()
    record = _issue(root, plan)

    assert verify_approval_authority(plan, record.receipt_id, root, now="2026-07-24T12:00:00Z").valid
    assert not verify_approval_authority(plan, record.receipt_id, {"records": {}}, now="2026-07-24T12:00:00Z")
    assert not verify_approval_authority(plan, record.receipt_id, None, now="2026-07-24T12:00:00Z")
    try:
        copy.copy(root)
    except TypeError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("authority roots must not be copied")


def test_self_generated_mapping_or_record_cannot_be_authority() -> None:
    plan = _plan()
    root = ApprovalAuthorityRoot()
    record = _issue(root, plan)
    copied = deepcopy(record.binding.canonical_payload())

    assert not verify_approval_authority(plan, copied, root)  # type: ignore[arg-type]
    try:
        ApprovalRecord()  # type: ignore[call-arg]
    except TypeError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("ApprovalRecord must only be minted by the root")


def test_stale_or_mutated_plan_is_rejected() -> None:
    plan = _plan()
    root = ApprovalAuthorityRoot()
    record = _issue(root, plan)

    mutated = deepcopy(plan)
    mutated["entries"][0]["destination"] = "raw/changed.csv"
    # The old self-referential digest is intentionally retained.
    assert not verify_approval_authority(mutated, record.receipt_id, root, now="2026-07-24T12:00:00Z")

    stale = deepcopy(plan)
    stale["digest"] = "0" * 64
    assert not verify_approval_authority(stale, record.receipt_id, root, now="2026-07-24T12:00:00Z")

    omitted = deepcopy(plan)
    omitted.pop("unresolved_proposals")
    omitted["digest"] = canonical_plan_digest(omitted)
    assert not verify_approval_authority(omitted, record.receipt_id, root, now="2026-07-24T12:00:00Z")


def test_expiry_and_revoke_are_fail_closed() -> None:
    plan = _plan()
    root = ApprovalAuthorityRoot()
    record = _issue(root, plan)

    assert not verify_approval_authority(plan, record.receipt_id, root, now="2026-07-25T00:00:00Z")
    root.revoke(record.receipt_id)
    assert not verify_approval_authority(plan, record.receipt_id, root, now="2026-07-24T12:00:00Z")


def test_supersede_marks_prior_record_non_current() -> None:
    plan = _plan()
    root = ApprovalAuthorityRoot()
    old = _issue(root, plan)
    replacement = _issue(root, plan, supersedes=old.receipt_id, issued_at="2026-07-24T01:00:00Z")

    assert not verify_approval_authority(plan, old.receipt_id, root, now="2026-07-24T12:00:00Z")
    assert verify_approval_authority(plan, replacement.receipt_id, root, now="2026-07-24T12:00:00Z").valid
