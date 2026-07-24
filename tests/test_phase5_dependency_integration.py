"""Focused Phase 5 coverage for normalization dependency evidence."""

from __future__ import annotations

from pathlib import Path

from hub_core.project_normalization import plan_normalize_project


def _tree_snapshot(root: Path) -> tuple[str, ...]:
    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


def _approved_analysis_mapping() -> list[dict[str, str]]:
    return [
        {
            "source": "scripts/analysis.py",
            "destination": "hub_scripts/analysis/analysis.py",
            "role": "script.analysis",
        }
    ]


def test_copy_plan_reports_hardcoded_dependency_for_approved_script(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "analysis.py"
    script.parent.mkdir()
    script.write_text("frame = read_csv('data/input.csv')\n", encoding="utf-8")

    plan = plan_normalize_project(
        project_path=tmp_path,
        move_policy="copy",
        approved_mappings=_approved_analysis_mapping(),
    )

    blockers = plan["hardcoded_unresolved_references"]
    assert any(
        blocker.get("kind") == "hardcoded_path"
        and blocker.get("path") == "data/input.csv"
        and blocker.get("script") == "scripts/analysis.py"
        for blocker in blockers
    )


def test_adopt_plan_is_read_only_while_previewing_script_dependencies(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "analysis.py"
    script.parent.mkdir()
    script.write_text("frame = read_csv('data/input.csv')\n", encoding="utf-8")
    before = _tree_snapshot(tmp_path)

    plan = plan_normalize_project(project_path=tmp_path, move_policy="adopt")

    assert plan["adopt_existing"] is True
    assert plan["entries"] == []
    assert plan["proposed_mappings"]
    assert _tree_snapshot(tmp_path) == before


def test_declared_raw_role_root_resolves_script_data_dependency(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "analysis.py"
    script.parent.mkdir()
    script.write_text("frame = read_csv('data/input.csv')\n", encoding="utf-8")
    (tmp_path / "project_config.yaml").write_text(
        "structure:\n  roots:\n    raw: data\n",
        encoding="utf-8",
    )

    plan = plan_normalize_project(
        project_path=tmp_path,
        move_policy="copy",
        approved_mappings=_approved_analysis_mapping(),
    )

    assert plan["hardcoded_unresolved_references"] == []


def test_unsupported_script_language_is_a_dependency_scan_blocker(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "analysis.jl"
    script.parent.mkdir()
    script.write_text("CSV.read(\"data/input.csv\")\n", encoding="utf-8")

    plan = plan_normalize_project(
        project_path=tmp_path,
        move_policy="copy",
        approved_mappings=[
            {
                "source": "scripts/analysis.jl",
                "destination": "hub_scripts/analysis/analysis.jl",
                "role": "script.analysis",
            }
        ],
    )

    assert any(
        blocker.get("kind") == "unsupported_language"
        and blocker.get("script") == "scripts/analysis.jl"
        for blocker in plan["hardcoded_unresolved_references"]
    )
    assert any(
        blocker.get("kind") == "dependency_scan_incomplete"
        and blocker.get("script") == "scripts/analysis.jl"
        for blocker in plan["hardcoded_unresolved_references"]
    )
