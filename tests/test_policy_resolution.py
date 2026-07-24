from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from hub_core.policy_resolution import (
    PolicyResolutionError,
    compatibility_resolved_policy,
    parse_policy_layers_json,
    resolve_policy_set,
)


def _layer(source: str, parameters: dict, policy_id: str | None = None) -> dict:
    return {
        "source": source,
        "policy_id": policy_id or f"{source}-policy",
        "version": "1",
        "parameters": parameters,
    }


KERNEL_INVARIANTS = (
    "path_containment",
    "schema_receipt_integrity",
    "runtime_result_disjointness",
    "no_replace_promotion",
)


def test_defaults_are_canonical_digestible_and_immutable() -> None:
    policy = resolve_policy_set([])
    render = policy.value("render_policy")

    assert render.value == "neutral"
    assert policy.value("path_containment").value is True
    assert policy.value("validation_target").value is None
    assert policy.canonical_sha256() == hashlib.sha256(policy.canonical_bytes()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        render.value = "nature"  # type: ignore[misc]


def test_render_validation_axes_project_to_legacy_resolved_policy() -> None:
    policy = resolve_policy_set(
        [_layer("render", {"render_policy": "neutral", "validation_target": "nature"})]
    )

    assert compatibility_resolved_policy(policy) == {
        "id": "journal-nature",
        "version": "1",
        "source": "policy-set-compatibility-projection",
        "parameters": {"render_policy": "render-neutral", "validation_target": "nature"},
    }


def test_research_ops_false_opt_out_preserves_current_project_fact() -> None:
    policy = resolve_policy_set(
        [_layer("project", {"require_figure_traceability": {"value": False, "opt_out": True}})]
    )
    traceability = policy.value("require_figure_traceability")

    assert traceability.value is False
    assert traceability.source == "project"
    assert traceability.opt_out_requested is True
    assert traceability.opt_out_accepted is True
    assert policy.value("require_canonical_docs").value is True


def test_research_ops_opt_out_only_records_explicit_source_and_digest_fact() -> None:
    default = resolve_policy_set([])
    policy = resolve_policy_set(
        [_layer("project", {"require_canonical_docs": {"opt_out": True}}, "project-config-policy")]
    )
    canonical_docs = policy.value("require_canonical_docs")

    assert canonical_docs.value is False
    assert canonical_docs.source == "explicit_project_opt_out"
    assert canonical_docs.policy_id == "project-config-policy"
    assert canonical_docs.opt_out_requested is True
    assert canonical_docs.opt_out_accepted is True
    assert canonical_docs.constraints[0].source == "explicit_project_opt_out"
    assert canonical_docs.constraints[0].value is False
    assert b"explicit_project_opt_out" in policy.canonical_bytes()
    assert policy.canonical_sha256() != default.canonical_sha256()


def test_higher_require_blocks_lower_opt_out_without_silent_override() -> None:
    policy = resolve_policy_set(
        [
            _layer("operator", {"require_figure_traceability": True}),
            _layer("project", {"require_figure_traceability": {"value": False, "opt_out": True}}),
        ]
    )
    traceability = policy.value("require_figure_traceability")

    assert traceability.value is True
    assert traceability.source == "operator"
    assert traceability.opt_out_requested is True
    assert traceability.opt_out_accepted is False


def test_kernel_invariants_are_not_opt_out_capable() -> None:
    with pytest.raises(PolicyResolutionError, match="path_containment immutable kernel invariant"):
        resolve_policy_set([_layer("project", {"path_containment": {"value": False, "opt_out": True}})])


@pytest.mark.parametrize("invariant", KERNEL_INVARIANTS)
@pytest.mark.parametrize(
    "disable_form",
    [
        False,
        {"value": False},
        {"value": False, "opt_out": True},
    ],
)
def test_kernel_invariants_reject_all_false_disable_forms(invariant: str, disable_form: object) -> None:
    with pytest.raises(PolicyResolutionError, match="immutable kernel invariant cannot be disabled"):
        resolve_policy_set([_layer("project", {invariant: disable_form})])


@pytest.mark.parametrize("invariant", KERNEL_INVARIANTS)
def test_kernel_invariants_reject_opt_out_only_disable_form(invariant: str) -> None:
    with pytest.raises(PolicyResolutionError, match="does not allow opt-out"):
        resolve_policy_set([_layer("project", {invariant: {"opt_out": True}})])


def test_selection_allowed_sets_only_narrow_and_conflict_fail_closed() -> None:
    with pytest.raises(PolicyResolutionError, match="empty allowed-set intersection"):
        resolve_policy_set(
            [
                _layer("operator", {"render_policy": {"allowed": ["nature"]}}),
                _layer("project", {"render_policy": {"allowed": ["nature", "science"]}}),
                _layer("render", {"render_policy": "science"}),
            ]
        )


def test_exact_and_equal_source_conflicts_fail_closed() -> None:
    with pytest.raises(PolicyResolutionError, match="exact values conflict"):
        resolve_policy_set(
            [
                _layer("lab", {"project_role": "module"}),
                _layer("project", {"project_role": "legacy"}),
            ]
        )
    with pytest.raises(PolicyResolutionError, match="duplicate policy source"):
        resolve_policy_set([_layer("project", {}), _layer("project", {}, "project-policy-2")])


def test_all_merge_operators_are_deterministic() -> None:
    policy = resolve_policy_set(
        [
            _layer(
                "operator",
                {
                    "minimum_raster_dpi": 300,
                    "maximum_physical_width_mm": 180,
                    "allowed_artifact_formats": {"allowed": ["png", "pdf"]},
                },
            ),
            _layer(
                "project",
                {
                    "minimum_raster_dpi": 600,
                    "maximum_physical_width_mm": 120,
                    "allowed_artifact_formats": {"allowed": ["png"]},
                },
            ),
        ]
    )

    assert policy.value("minimum_raster_dpi").value == 600
    assert policy.value("maximum_physical_width_mm").value == 120
    assert policy.value("allowed_artifact_formats").value == ["png"]


def test_unknown_duplicate_nonfinite_and_path_like_inputs_are_rejected() -> None:
    with pytest.raises(PolicyResolutionError, match="duplicate key"):
        parse_policy_layers_json(
            b'[{"source":"project","source":"project","policy_id":"p","version":"1","parameters":{}}]'
        )
    with pytest.raises(PolicyResolutionError, match="non-finite"):
        resolve_policy_set(
            b'[{"source":"project","policy_id":"p","version":"1","parameters":{"minimum_raster_dpi":NaN}}]'
        )
    with pytest.raises(PolicyResolutionError, match="unsupported or missing"):
        resolve_policy_set([_layer("project", {"unknown_axis": True})])
    with pytest.raises(PolicyResolutionError, match="path-like"):
        resolve_policy_set([_layer("project", {"project_role": "C:/research/project"})])


def test_exceptions_are_recorded_but_do_not_change_resolved_values() -> None:
    policy = resolve_policy_set(
        [
            _layer(
                "project",
                {
                    "require_canonical_docs": {
                        "value": True,
                        "exceptions": [
                            {"finding_code": "CANONICAL_DOC_EVIDENCE_INVALID", "subject_digest": "a" * 64}
                        ],
                    }
                },
            )
        ]
    )
    canonical_docs = policy.value("require_canonical_docs")

    assert canonical_docs.value is True
    assert canonical_docs.exceptions[0].finding_code == "CANONICAL_DOC_EVIDENCE_INVALID"
    assert canonical_docs.exceptions[0].subject_digest == "a" * 64


def test_canonical_digest_is_stable_for_equivalent_mapping_order() -> None:
    left = resolve_policy_set([_layer("render", {"render_policy": "neutral", "validation_target": "nature"})])
    right = resolve_policy_set([_layer("render", {"validation_target": "nature", "render_policy": "neutral"})])

    assert left.canonical_bytes() == right.canonical_bytes()
    assert left.canonical_sha256() == right.canonical_sha256()
