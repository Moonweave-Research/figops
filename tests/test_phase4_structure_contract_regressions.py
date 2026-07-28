"""Focused Phase 4 regression coverage for reviewed structure operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.mcp import GraphHubMCPServer
from hub_core.project_normalization import plan_normalize_project
from hub_core.structure_path_security import capture_project_root
from hub_core.structure_plan import (
    build_structure_plan,
    canonical_plan_digest,
    confirmation_token,
)
from hub_core.structure_role_binding import validate_role_destination_bindings


def _tree_snapshot(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if "__pycache__" not in path.parts
        )
    )


def _structured(response: dict) -> dict:
    return response["structuredContent"]


def test_plan_digest_and_token_are_stable_for_semantically_identical_plans(tmp_path: Path) -> None:
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "a.csv").write_bytes(b"a\n1\n")
    (tmp_path / "legacy" / "b.csv").write_bytes(b"b\n2\n")
    mappings = [
        {"source": "legacy/a.csv", "destination": "raw/a.csv", "role": "raw"},
        {"source": "legacy/b.csv", "destination": "raw/b.csv", "role": "raw"},
    ]

    first = build_structure_plan(tmp_path, mappings)
    second = build_structure_plan(tmp_path, list(reversed(mappings)))

    assert canonical_plan_digest(first) == canonical_plan_digest(second)
    assert first["digest"] == second["digest"]
    assert confirmation_token(first) == confirmation_token(second)

    # Presentation-only dictionary ordering must not change the reviewed identity.
    reordered = json.loads(json.dumps(second, ensure_ascii=False))
    reordered = {key: reordered[key] for key in reversed(list(reordered))}
    assert canonical_plan_digest(first) == canonical_plan_digest(reordered)


@pytest.mark.parametrize(
    "malformed",
    [
        {"path": "structure.roots.raw", "before": "raw", "after": "raw"},
        {"path": [], "before": "raw", "after": "raw"},
        {"path": ["structure", True], "before": "raw", "after": "raw"},
        {"path": ["structure", "roots", "raw"], "before": "raw"},
    ],
)
def test_build_structure_plan_rejects_malformed_config_diff(tmp_path: Path, malformed: dict) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"x\n1\n")

    with pytest.raises(ValueError):
        build_structure_plan(
            tmp_path,
            [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
            config_diff=[malformed],
        )


def test_validate_role_destination_bindings_rejects_unknown_role(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown structure role"):
        validate_role_destination_bindings(
            tmp_path,
            [{"role": "script.unknown", "destination": "hub_scripts/analysis/x.py"}],
            config_path=tmp_path / "project_config.yaml",
            config_update=None,
            root_identity=capture_project_root(tmp_path),
            planned_hash=None,
        )


@pytest.mark.parametrize("destination", ["hub_scripts/figures/x.py", "outside/x.py"])
def test_validate_role_destination_bindings_rejects_sibling_or_outside_destination(
    tmp_path: Path, destination: str
) -> None:
    with pytest.raises(ValueError, match="not bound"):
        validate_role_destination_bindings(
            tmp_path,
            [{"role": "script.analysis", "destination": destination}],
            config_path=tmp_path / "project_config.yaml",
            config_update=None,
            root_identity=capture_project_root(tmp_path),
            planned_hash=None,
        )


def test_plan_normalize_copy_requires_approvals_but_adopt_is_read_only(tmp_path: Path) -> None:
    source = tmp_path / "plot.py"
    source.write_text("print('plot')\n", encoding="utf-8")
    before = _tree_snapshot(tmp_path)

    with pytest.raises(ValueError, match="approved_mappings"):
        plan_normalize_project(project_path=tmp_path, move_policy="copy")

    adopted = plan_normalize_project(project_path=tmp_path, move_policy="adopt")

    assert adopted["adopt_existing"] is True
    assert adopted["entries"] == []
    assert _tree_snapshot(tmp_path) == before


def test_normalize_project_structure_apply_requires_exact_confirmation_token(tmp_path: Path) -> None:
    project = tmp_path / "LegacyGraph"
    project.mkdir()
    (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=tmp_path)
    arguments = {
        "project_path": str(project),
        "move_policy": "copy",
        "approved_mappings": [
            {"source": "plot.py", "destination": "hub_scripts/figures/plot.py", "role": "script.figure"}
        ],
    }

    planned = _structured(server.call_tool("figops.normalize_project_structure", {**arguments, "dry_run": True}))
    rejected = _structured(
        server.call_tool(
            "figops.normalize_project_structure",
            {**arguments, "dry_run": False, "confirmation_token": planned["confirmation_token"] + "x"},
        )
    )

    assert rejected["status"] == "error"
    assert rejected["error_code"] == "FIGOPS_NORMALIZATION_PLAN_REJECTED"
    assert not (project / "hub_scripts" / "figures" / "plot.py").exists()

    applied = _structured(
        server.call_tool(
            "figops.normalize_project_structure",
            {**arguments, "dry_run": False, "confirmation_token": planned["confirmation_token"]},
        )
    )
    assert applied["status"] in {"ok", "warning"}
    assert (project / "hub_scripts" / "figures" / "plot.py").read_text(encoding="utf-8") == "print('plot')\n"
