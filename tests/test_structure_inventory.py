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
