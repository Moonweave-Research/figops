from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hub_core.structure_audit import audit_project_structure
from hub_core.structure_contract_types import DEFAULT_V11_ROOTS
from hub_core.structure_inventory import build_structure_inventory


def _config() -> dict[str, object]:
    return {
        "structure": {"contract": "figops-project-v1.1", "roots": dict(DEFAULT_V11_ROOTS)},
        "pipeline": {
            "analysis": [
                {
                    "script": "hub_scripts/analysis/run.py",
                    "inputs": ["raw/input.csv"],
                    "outputs": ["results/data/intermediate/clean.csv"],
                }
            ]
        },
        "figures": [
            {
                "script": "hub_scripts/figures/plot.py",
                "inputs": ["results/data/intermediate/clean.csv"],
                "output": "results/figures/Fig1.png",
            }
        ],
    }


def test_inventory_is_declared_first_and_deterministic(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/input.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "hub_scripts/analysis").mkdir(parents=True)
    (tmp_path / "hub_scripts/analysis/run.py").write_text("", encoding="utf-8")
    (tmp_path / "mystery.py").write_text("", encoding="utf-8")

    first = build_structure_inventory(tmp_path, _config())
    second = build_structure_inventory(tmp_path, _config())

    assert first == second
    assert first["roles"]["analysis_scripts"]["paths"] == ["hub_scripts/analysis/run.py"]
    mystery = next(item for item in first["unknowns"] if item["path"] == "mystery.py")
    assert mystery["candidate"] == {
        "candidate_role": "unknown",
        "confidence": 0.4,
        "reason": "ambiguous candidates: analysis_scripts, figure_scripts, shared_scripts",
    }
    assert any(item["code"] == "stale_reference" for item in first["findings"])


def test_audit_is_diagnostic_only_and_flags_raw_output(tmp_path: Path) -> None:
    for path in DEFAULT_V11_ROOTS.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    config = _config()
    config["figures"] = [{"output": "raw/generated.png"}]

    audit = audit_project_structure(tmp_path, config)

    assert audit["proposed_changes"] == []
    assert any(item["code"] == "raw_output" for item in audit["findings"])


def test_configured_reference_precedes_extension_and_name_heuristics(tmp_path: Path) -> None:
    config = _config()
    config["pipeline"] = {"analysis": [{"script": "legacy/plot.py"}]}
    script = tmp_path / "legacy" / "plot.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    inventory = build_structure_inventory(tmp_path, config)

    unknown = next(item for item in inventory["unknowns"] if item["path"] == "legacy/plot.py")
    assert unknown["candidate"] == {
        "candidate_role": "analysis_scripts",
        "confidence": 1.0,
        "reason": "configured relationship declares the semantic role",
    }


def test_conflicting_configured_relationships_remain_unknown_for_review(tmp_path: Path) -> None:
    config = _config()
    config["pipeline"] = {"analysis": [{"script": "legacy/plot.py"}]}
    config["figures"] = [{"script": "legacy/plot.py"}]
    script = tmp_path / "legacy" / "plot.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    audit = audit_project_structure(tmp_path, config)

    unknown = next(item for item in audit["unknowns"] if item["path"] == "legacy/plot.py")
    assert unknown["candidate"] == {
        "candidate_role": "unknown",
        "confidence": 1.0,
        "reason": "ambiguous configured relationships: analysis_scripts, figure_scripts",
    }


def test_inventory_ignores_metadata_scalars_and_dotted_module_names(tmp_path: Path) -> None:
    config = _config()
    config["schema_version"] = "1.1"
    config["project"] = {"description": "Public-safe fixture for materials/polymer analysis."}
    config["pipeline"] = {
        "analysis": [
            {
                "domain_helper": "materials_polymer.signal_smooth_baseline",
                "inputs": ["raw/input.csv"],
                "outputs": ["results/data/intermediate/clean.csv"],
            }
        ]
    }

    inventory = build_structure_inventory(tmp_path, config)
    ignored = {
        "1.1",
        "Public-safe fixture for materials/polymer analysis.",
        "materials_polymer.signal_smooth_baseline",
    }
    graph_ids = {node["id"] for node in inventory["graph"]["nodes"]}

    assert graph_ids.isdisjoint(ignored)
    assert all(item.get("path") not in ignored for item in inventory["findings"])


def test_inventory_walks_explicit_file_references_without_suffixes(tmp_path: Path) -> None:
    config = _config()
    config["pipeline"] = {
        "analysis": [
            {
                "script": "analysis_runner",
                "inputs": ["input_dataset"],
                "outputs": ["derived_result"],
            }
        ]
    }

    inventory = build_structure_inventory(tmp_path, config)
    graph_ids = {node["id"] for node in inventory["graph"]["nodes"]}

    assert {"analysis_runner", "input_dataset", "derived_result"} <= graph_ids


def test_audit_compares_declared_roots_with_actual_paths_and_nested_configs(tmp_path: Path) -> None:
    config = _config()
    (tmp_path / "project_config.yaml").write_text("project: {}\n", encoding="utf-8")
    (tmp_path / "raw").mkdir()
    (tmp_path / "unmanaged").mkdir()
    (tmp_path / "unmanaged" / "notes.txt").write_text("layout evidence\n", encoding="utf-8")
    nested_config = tmp_path / "figops_nested" / "project_config.yaml"
    nested_config.parent.mkdir()
    nested_config.write_text("project: {}\n", encoding="utf-8")

    audit = audit_project_structure(tmp_path, config, config_path="project_config.yaml")
    declared_vs_actual = audit["declared_vs_actual"]

    missing = {item["role"] for item in declared_vs_actual["declared_roots"] if not item["exists"]}
    undeclared = {(item["path"], item["kind"]) for item in declared_vs_actual["undeclared_paths"]}

    assert {"scripts", "results"} <= missing
    assert ("unmanaged", "directory") in undeclared
    assert ("unmanaged/notes.txt", "file") not in undeclared
    assert declared_vs_actual["nested_project_configs"] == ["figops_nested/project_config.yaml"]
    assert any(
        item["code"] == "nested_project_config" and item["path"] == "figops_nested/project_config.yaml"
        for item in audit["findings"]
    )


def test_inventory_uses_declared_first_scandir_without_path_rglob(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "input.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "unmanaged" / "deep").mkdir(parents=True)
    (tmp_path / "unmanaged" / "deep" / "ignored.csv").write_text("x\n2\n", encoding="utf-8")

    with patch.object(Path, "rglob", side_effect=AssertionError("Path.rglob must not be used")):
        inventory = build_structure_inventory(tmp_path, _config())

    assert inventory["roles"]["raw"]["paths"] == ["raw/input.csv"]
    assert any(item["path"] == "unmanaged" for item in inventory["unknowns"])
    assert all(item["path"] != "unmanaged/deep/ignored.csv" for item in inventory["unknowns"])


def test_inventory_stops_at_entry_ceiling_and_reports_partial_result(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    for index in range(5):
        (tmp_path / "raw" / f"input-{index}.csv").write_text("x\n1\n", encoding="utf-8")

    inventory = build_structure_inventory(tmp_path, _config(), max_entries=3)

    ceiling = next(item for item in inventory["findings"] if item["code"] == "inventory_entry_limit")
    assert ceiling == {"code": "inventory_entry_limit", "entry_count": 3, "max_entries": 3}
    assert len(inventory["roles"]["raw"]["paths"]) <= 3


def test_declared_figure_input_is_not_reported_as_an_orphan(tmp_path: Path) -> None:
    for path in DEFAULT_V11_ROOTS.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    source = tmp_path / 'results/data/source/known.csv'
    source.write_text('x,y\n1,2\n', encoding='utf-8')
    config = _config()
    config['figures'][0]['inputs'] = ['results/data/source/known.csv']

    inventory = build_structure_inventory(tmp_path, config)

    assert not any(
        finding['code'] == 'orphan' and finding['path'] == 'results/data/source/known.csv'
        for finding in inventory['findings']
    )


def test_grouping_roots_with_only_declared_subdirectories_are_not_stale(tmp_path: Path) -> None:
    for path in DEFAULT_V11_ROOTS.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    config = _config()
    config["pipeline"] = {}
    config["figures"] = []

    inventory = build_structure_inventory(tmp_path, config)

    assert not any(finding["code"] == "stale_reference" for finding in inventory["findings"])
    assert all(node["exists"] for node in inventory["graph"]["nodes"])


def test_large_raw_tree_does_not_starve_small_nested_roles(tmp_path: Path) -> None:
    for path in DEFAULT_V11_ROOTS.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    for index in range(200):
        (tmp_path / "raw" / f"frame-{index:03d}.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "results/data/source/rare.csv").write_text("x\n2\n", encoding="utf-8")
    (tmp_path / "results/figures/rare.png").write_bytes(b"fixture")
    config = _config()
    config["pipeline"] = {}
    config["figures"] = []

    inventory = build_structure_inventory(tmp_path, config, max_entries=64)

    assert inventory["roles"]["source_data"]["paths"] == ["results/data/source/rare.csv"]
    assert inventory["roles"]["figures"]["paths"] == ["results/figures/rare.png"]
    assert any(finding["code"] == "inventory_entry_limit" for finding in inventory["findings"])


def test_partial_inventory_marks_inferences_but_keeps_missing_references_definite(tmp_path: Path) -> None:
    for path in DEFAULT_V11_ROOTS.values():
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    for index in range(200):
        (tmp_path / "raw" / f"frame-{index:03d}.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("unclassified", encoding="utf-8")
    (tmp_path / "results/figures/unreferenced.png").write_bytes(b"fixture")
    config = _config()

    inventory = build_structure_inventory(tmp_path, config, max_entries=64)

    assert inventory["declared_vs_actual"]["inventory_complete"] is False
    orphans = [finding for finding in inventory["findings"] if finding["code"] == "orphan"]
    assert orphans and all(finding["provisional"] for finding in orphans)
    assert inventory["unknowns"] and all(item["provisional"] for item in inventory["unknowns"])
    missing = next(finding for finding in inventory["findings"] if finding.get("path") == "raw/input.csv")
    assert missing["code"] == "stale_reference"
    assert not missing.get("provisional", False)


def test_complete_inventory_keeps_real_orphans_and_does_not_false_flag_exact_budget(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    for index in range(5):
        (tmp_path / "raw" / f"frame-{index}.csv").write_text("x\n1\n", encoding="utf-8")
    config = _config()
    inventory = build_structure_inventory(tmp_path, config, max_entries=6)

    assert inventory["declared_vs_actual"]["inventory_complete"] is True
    assert not any(finding["code"] == "inventory_entry_limit" for finding in inventory["findings"])
    (tmp_path / "results/figures").mkdir(parents=True)
    (tmp_path / "results/figures/unreferenced.png").write_bytes(b"fixture")
    inventory = build_structure_inventory(tmp_path, config)
    orphan = next(finding for finding in inventory["findings"] if finding["code"] == "orphan")
    assert orphan["path"] == "results/figures/unreferenced.png"
    assert not orphan.get("provisional", False)


def test_fair_scan_does_not_enter_nested_roles_through_a_symlink_parent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    (outside / "analysis").mkdir(parents=True)
    (outside / "analysis/private.csv").write_text("outside fixture", encoding="utf-8")
    (project / "hub_scripts").symlink_to(outside, target_is_directory=True)
    import os
    original = os.scandir

    def contained_scandir(path):
        assert Path(path).resolve().is_relative_to(project), path
        return original(path)

    with patch("hub_core.structure_inventory.os.scandir", contained_scandir):
        with pytest.raises(ValueError, match="resolves outside the project root"):
            build_structure_inventory(project, _config())
