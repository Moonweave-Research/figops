from __future__ import annotations

from pathlib import Path

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
