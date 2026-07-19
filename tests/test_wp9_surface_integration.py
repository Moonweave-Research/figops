from __future__ import annotations

import json
from pathlib import Path

from hub_core.mcp import FigOpsMCPServer


def _server(root: Path, *, profile: str = "v2") -> FigOpsMCPServer:
    return FigOpsMCPServer(
        research_root=root,
        runtime_root=root.parent / f"{root.name}-runtime",
        surface_profile=profile,
        write_tools_enabled=False,
    )


def _project(root: Path, *, access_class: str | None = None) -> tuple[Path, Path]:
    project = root / "project"
    data = project / "raw" / "facts.csv"
    data.parent.mkdir(parents=True)
    data.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
    access = f"\n      access_class: {access_class}" if access_class else ""
    (project / "project_config.yaml").write_text(
        "schema_version: '1.1'\n"
        "project:\n  name: Example\n"
        "data_contract:\n  csv_checks:\n"
        f"    - path: raw/facts.csv{access}\n",
        encoding="utf-8",
    )
    return project, data


def test_v2_describe_project_structure_is_read_only_and_versioned(tmp_path: Path) -> None:
    project, _ = _project(tmp_path)
    before = {item.relative_to(project).as_posix(): item.read_bytes() for item in project.rglob("*") if item.is_file()}

    result = _server(tmp_path).call_tool(
        "figops.describe", {"kind": "project_structure", "project_path": str(project)}
    )["structuredContent"]

    assert result["schema_version"] == "figops.project-structure-audit.v1"
    assert result["status_code"] in {"PROJECT_STRUCTURE_OK", "PROJECT_STRUCTURE_REVIEW_REQUIRED"}
    assert set(("roles", "graph", "findings", "unknowns", "proposed_changes")) <= result.keys()
    assert result["proposed_changes"] == []
    assert str(tmp_path.resolve()) not in json.dumps(result)
    assert before == {
        item.relative_to(project).as_posix(): item.read_bytes() for item in project.rglob("*") if item.is_file()
    }


def test_restricted_and_unspecified_data_are_metadata_only(tmp_path: Path) -> None:
    for access_class, expected_code in (
        ("restricted", "INSPECTION_METADATA_ONLY_RESTRICTED"),
        (None, "INSPECTION_METADATA_ONLY_UNSPECIFIED"),
    ):
        root = tmp_path / (access_class or "unspecified")
        project, data = _project(root, access_class=access_class)
        result = _server(root).call_tool(
            "figops.inspect_data",
            {"data_path": str(data), "include_samples": True, "sample_rows": 2},
        )["structuredContent"]
        assert project.exists()
        assert result["status_code"] == expected_code
        assert result["access_policy"]["mode"] == "metadata_only"
        assert result["columns"] == []
        assert result["sample_columns"] == []
        assert result["samples"] == []


def test_public_data_requires_explicit_opt_in_for_bounded_values(tmp_path: Path) -> None:
    _, data = _project(tmp_path, access_class="public")
    server = _server(tmp_path)

    default = server.call_tool("figops.inspect_data", {"data_path": str(data)})["structuredContent"]
    opted_in = server.call_tool(
        "figops.inspect_data", {"data_path": str(data), "include_samples": True, "sample_rows": 1}
    )["structuredContent"]

    assert default["status_code"] == "INSPECTION_METADATA_ONLY_DEFAULT"
    assert default["columns"] == []
    assert opted_in["status_code"] == "INSPECTION_VALUES_AVAILABLE"
    assert opted_in["access_policy"]["classification"] == "public"
    assert opted_in["samples"] == [["1", "10"]]
