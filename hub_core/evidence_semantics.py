"""Cross-field semantic checks for the frozen evidence envelope."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, NoReturn

Fail = Callable[[str, str, str], NoReturn]
_POLICY_STATUSES = {"blocked", "needs_revision", "needs_review", "informational"}


def validate_cross_evidence_consistency(root: Mapping[str, Any], fail: Fail) -> None:
    """Reject internally contradictory facts after structural validation."""

    for index, projection in enumerate(root.get("policy_projections", [])):
        if "status" in projection and projection["status"] not in _POLICY_STATUSES:
            fail(
                "POLICY_STATUS_INVALID",
                f"evidence.policy_projections[{index}].status",
                "has an invalid value",
            )

    exact = root.get("exact_reproducibility")
    if isinstance(exact, Mapping) and exact.get("status") in {"same", "different"}:
        if str(exact.get("algorithm") or "").lower() != "sha256":
            fail(
                "EXACT_ALGORITHM_INVALID",
                "evidence.exact_reproducibility.algorithm",
                "must be sha256",
            )
        hashes_equal = str(exact["reference_sha256"]).lower() == str(exact["candidate_sha256"]).lower()
        if (exact["status"] == "same") != hashes_equal:
            fail(
                "EXACT_STATUS_CONFLICT",
                "evidence.exact_reproducibility.status",
                "conflicts with the reference and candidate hashes",
            )

    entries = root.get("artifacts", {}).get("entries", [])
    roles = {
        entry.get("logical_role")
        for entry in entries
        if isinstance(entry, Mapping)
    }
    visual = root.get("visual_comparison")
    if isinstance(visual, Mapping) and visual.get("status") == "available":
        for field in ("reference_artifact", "candidate_artifact"):
            if visual.get(field) not in roles:
                fail(
                    "VISUAL_ARTIFACT_UNKNOWN",
                    f"evidence.visual_comparison.{field}",
                    "must reference a verified artifact logical_role",
                )

    primary = [
        entry
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("logical_role") == "primary"
    ]
    output_sha256 = root.get("provenance", {}).get("output_sha256")
    if len(primary) == 1 and isinstance(output_sha256, str):
        if output_sha256.lower() != str(primary[0]["sha256"]).lower():
            fail(
                "PRIMARY_OUTPUT_HASH_CONFLICT",
                "evidence.provenance.output_sha256",
                "must match the explicit primary artifact sha256",
            )
