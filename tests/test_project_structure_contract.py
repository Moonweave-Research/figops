from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hub_core.config_language_policy import get_language_policy
from hub_core.config_parser import validate_config
from hub_core.project_structure_contract import resolve_project_structure, structure_diagnostics
from hub_core.structure_contract_types import CURRENT_CONTRACT, DEFAULT_V11_ROOTS, StructureContractError


def _current_config() -> dict:
    return {
        "schema_version": "1.1",
        "project": {"name": "v1.1 study", "target_journal": "Nature Communications"},
        "structure": {"contract": CURRENT_CONTRACT, "roots": dict(DEFAULT_V11_ROOTS)},
        "visual_style": {"render_policy": "neutral", "validation_target": "nature"},
    }


def test_v11_role_nesting_dag_rejects_forbidden_aliases() -> None:
    config = _current_config()
    config["structure"]["roots"]["figures"] = "results/tables/figures"

    with pytest.raises(StructureContractError):
        resolve_project_structure(config)


def test_legacy_diagnostics_preserve_results_data_discovery_ambiguity() -> None:
    diagnostics = structure_diagnostics({"project": {"name": "legacy"}})

    assert diagnostics["declared_version"] == "1.0"
    assert diagnostics["effective_version"] == "1.1"
    assert diagnostics["legacy_discovery_roots"] == {
        "intermediate": "results/data",
        "source_data": "results/data",
    }
    assert "--dry-run" in diagnostics["compatibility_warning"]


def test_v11_structure_rejects_runtime_and_unknown_structure_fields() -> None:
    config = _current_config()
    config["structure"]["roots"]["runtime"] = ".runtime"
    config["structure"]["runtime_root"] = ".runtime"

    errors = validate_config(config)

    assert any("structure contains unsupported fields" in error for error in errors)


def test_existing_symlink_role_root_must_remain_project_contained(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    try:
        (tmp_path / "raw").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(StructureContractError, match="outside the project root"):
        resolve_project_structure(_current_config(), project_root=tmp_path)


def test_external_raw_descriptors_are_separate_and_producer_references_are_typed() -> None:
    config = _current_config()
    config["external_raw"] = [
        {
            "id": "instrument-run",
            "uri": "gdrive://lab/run.csv",
            "allowed_root": "lab-exports",
            "version": "etag-1",
            "sha256": "a" * 64,
        }
    ]
    config["pipeline"] = {
        "analysis": [
            {
                "script": "hub_scripts/analysis/analyze.py",
                "lang": "python",
                "inputs": ["external_raw:instrument-run"],
                "outputs": ["results/data/source/summary.csv"],
            }
        ]
    }

    assert validate_config(config) == []
    config["pipeline"]["analysis"][0]["inputs"] = ["external_raw:missing"]
    assert any("unknown external raw input" in error for error in validate_config(config))


@pytest.mark.parametrize(
    "declaration",
    [[], {"type": "no_raw_inputs", "reason": ""}, {"type": "wrong", "reason": "synthetic"}],
)
def test_no_raw_inputs_requires_typed_nonempty_declaration(declaration: object) -> None:
    config = _current_config()
    config["data_contract"] = {
        "require_figure_traceability": False,
        "raw_integrity": {"mode": "strict", "paths": [], "no_raw_inputs": declaration},
    }

    assert any("no_raw_inputs" in error for error in validate_config(config))


def test_new_language_policy_is_advisory_auto_while_legacy_keeps_preferences() -> None:
    current = _current_config()
    current["pipeline"] = {
        "analysis": [
            {
                "script": "hub_scripts/analysis/analyze.jl",
                "lang": "julia",
                "outputs": ["results/data/intermediate/output.csv"],
            }
        ]
    }
    assert get_language_policy(current) == {
        "analysis_lang": "auto",
        "plot_lang": "auto",
        "allow_nonstandard": True,
        "mode": "advisory",
        "compatibility": False,
    }
    assert not any("language 'julia' violates policy" in error for error in validate_config(current))

    legacy = {"project": {"name": "legacy"}}
    policy = get_language_policy(legacy)
    assert policy["analysis_lang"] == "r"
    assert policy["plot_lang"] == "python"
    assert policy["allow_nonstandard"] is False


def test_validation_target_matches_journal_but_is_independent_of_render_policy() -> None:
    config = _current_config()
    assert validate_config(config) == []

    config["visual_style"]["validation_target"] = "science"
    errors = validate_config(config)
    assert any("target_journal" in error and "inconsistent" in error for error in errors)


@pytest.mark.parametrize(
    "template_path",
    [Path("project_config_template.yaml"), Path("hub_core/templates/project_config_template.yaml")],
)
def test_v11_templates_declare_canonical_roles_and_nonvacuous_strict_raw(template_path: Path) -> None:
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert config["schema_version"] == "1.1"
    assert config["structure"]["roots"] == dict(DEFAULT_V11_ROOTS)
    raw = config["data_contract"]["raw_integrity"]
    assert raw["mode"] == "strict"
    assert raw["paths"]
    assert config["pipeline"]["analysis"][0]["inputs"] == ["raw/example.csv"]
    assert validate_config(config) == []
