from pathlib import Path

from scripts.project_figure_inventory import build_inventory, render_markdown


def _write_project(root: Path, name: str) -> Path:
    project = root / name
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "results" / "figures").mkdir(parents=True)
    (project / "hub_scripts" / "plot.py").write_text("print('plot')\n", encoding="utf-8")
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n", encoding="utf-8")
    (project / "project_config.yaml").write_text(
        """
project:
  name: Inventory Fixture
visual_style:
  target_format: nature
  profile: baseline
figures:
  - id: FigReady
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/FigReady.png
  - id: FigMissing
    script: hub_scripts/plot.py
    inputs: ["results/data/missing.csv"]
    output: results/figures/FigMissing.png
""",
        encoding="utf-8",
    )
    return project


def test_build_inventory_marks_render_candidates(tmp_path: Path) -> None:
    _write_project(tmp_path, "project_a")

    entries = build_inventory(tmp_path)
    by_id = {entry.figure_id: entry for entry in entries}

    assert by_id["FigReady"].render_candidate is True
    assert by_id["FigReady"].project_path == "project_a"
    assert by_id["FigReady"].target_format == "nature"
    assert by_id["FigMissing"].render_candidate is False
    assert by_id["FigMissing"].missing_inputs == ("results/data/missing.csv",)


def test_build_inventory_normalizes_korean_paths_to_nfc(tmp_path: Path) -> None:
    decomposed_name = "그래프 측정"
    project = _write_project(tmp_path, decomposed_name)

    entry = build_inventory(tmp_path)[0]

    assert entry.project_path == "그래프 측정"
    assert project.exists()


def test_build_inventory_follows_symlinked_project_directories(tmp_path: Path) -> None:
    external = tmp_path / "external" / "project_a"
    _write_project(external.parent, "project_a")
    root = tmp_path / "ResearchOS"
    root.mkdir()
    (root / "project_a").symlink_to(external, target_is_directory=True)

    entries = build_inventory(root)

    assert {entry.project_path for entry in entries} == {"project_a"}
    assert {entry.figure_id for entry in entries} == {"FigReady", "FigMissing"}


def test_build_inventory_resolves_legacy_scripts_config_from_project_root(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "legacy_project")
    scripts_dir = project / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "project_config.yaml").write_text((project / "project_config.yaml").read_text(encoding="utf-8"))
    (project / "project_config.yaml").unlink()

    entries = build_inventory(tmp_path)
    by_id = {entry.figure_id: entry for entry in entries}

    assert by_id["FigReady"].project_path == "legacy_project"
    assert by_id["FigReady"].render_candidate is True


def test_build_inventory_finds_legacy_config_at_max_project_depth(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "a" / "b" / "c", "d")
    scripts_dir = project / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "project_config.yaml").write_text((project / "project_config.yaml").read_text(encoding="utf-8"))
    (project / "project_config.yaml").unlink()

    entries = build_inventory(tmp_path, max_depth=4)

    assert {entry.project_path for entry in entries} == {"a/b/c/d"}


def test_build_inventory_matches_mcp_script_entrypoint_and_input_alias(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    config = project / "project_config.yaml"
    config.write_text(
        """
project:
  name: Inventory Fixture
visual_style:
  target_format: nature
figures:
  - id: FigEntrypoint
    script: hub_scripts/plot.py::main
    input: results/data/summary.csv
    output: results/figures/FigEntrypoint.png
""",
        encoding="utf-8",
    )

    entry = build_inventory(tmp_path)[0]

    assert entry.script == "hub_scripts/plot.py::main"
    assert entry.input_count == 1
    assert entry.render_candidate is True


def test_build_inventory_does_not_mark_script_directories_as_candidates(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    (project / "hub_scripts" / "plot.py").unlink()
    (project / "hub_scripts" / "plot.py").mkdir()

    ready = next(entry for entry in build_inventory(tmp_path) if entry.figure_id == "FigReady")

    assert ready.script_exists is False
    assert ready.render_candidate is False


def test_build_inventory_reports_invalid_configs(tmp_path: Path) -> None:
    project = tmp_path / "project_a"
    project.mkdir()
    (project / "project_config.yaml").write_text("project: [\n", encoding="utf-8")

    entries = build_inventory(tmp_path)

    assert len(entries) == 1
    assert entries[0].figure_id == "(config error)"
    assert entries[0].render_candidate is False
    assert "Invalid YAML" in entries[0].config_error


def test_build_inventory_reports_schema_invalid_configs(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    config = project / "project_config.yaml"
    config.write_text(
        """
visual_style:
  target_format: nature
figures:
  - id: FigReady
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/FigReady.png
""",
        encoding="utf-8",
    )

    entries = build_inventory(tmp_path)

    assert len(entries) == 1
    assert entries[0].figure_id == "(config error)"
    assert entries[0].render_candidate is False
    assert "project" in entries[0].config_error


def test_build_inventory_does_not_mark_invalid_project_paths_as_candidates(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    config = project / "project_config.yaml"
    config.write_text(
        f"""
project:
  name: Inventory Fixture
visual_style:
  target_format: nature
figures:
  - id: FigAbsoluteScript
    script: {project / "hub_scripts" / "plot.py"}
    output: results/figures/FigAbsoluteScript.png
  - id: FigTraversalOutput
    script: hub_scripts/plot.py
    output: ../outside.png
""",
        encoding="utf-8",
    )

    by_id = {entry.figure_id: entry for entry in build_inventory(tmp_path)}

    assert by_id["FigAbsoluteScript"].render_candidate is False
    assert by_id["FigAbsoluteScript"].invalid_paths[0].startswith("script: ")
    assert by_id["FigTraversalOutput"].render_candidate is False
    assert by_id["FigTraversalOutput"].invalid_paths == ("output: ../outside.png",)


def test_build_inventory_does_not_mark_paths_escaping_project_root_as_candidates(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    external_scripts = tmp_path / "external_scripts"
    external_scripts.mkdir()
    (external_scripts / "plot.py").write_text("print('outside')\n", encoding="utf-8")
    (project / "linked_scripts").symlink_to(external_scripts, target_is_directory=True)
    (project / "project_config.yaml").write_text(
        """
project:
  name: Inventory Fixture
visual_style:
  target_format: nature
figures:
  - id: FigEscapes
    script: linked_scripts/plot.py
    output: results/figures/FigEscapes.png
""",
        encoding="utf-8",
    )

    entry = build_inventory(tmp_path)[0]

    assert entry.render_candidate is False
    assert entry.invalid_paths == ("script: linked_scripts/plot.py",)


def test_build_inventory_marks_symlinked_config_as_non_candidate(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    config = project / "project_config.yaml"
    target = tmp_path / "external_config.yaml"
    target.write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    config.unlink()
    config.symlink_to(target)

    ready = next(entry for entry in build_inventory(tmp_path) if entry.figure_id == "FigReady")

    assert ready.render_candidate is False
    assert ready.symlinked_paths == ("project_config.yaml",)


def test_build_inventory_does_not_mark_symlinked_inputs_as_candidates(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    data_path = project / "results" / "data" / "summary.csv"
    target = tmp_path / "external_summary.csv"
    target.write_text(data_path.read_text(encoding="utf-8"), encoding="utf-8")
    data_path.unlink()
    data_path.symlink_to(target)

    entries = build_inventory(tmp_path)
    ready = next(entry for entry in entries if entry.figure_id == "FigReady")

    assert ready.render_candidate is False
    assert ready.symlinked_paths == ("results/data/summary.csv",)


def test_build_inventory_does_not_mark_symlinked_results_data_tree_as_candidate(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    data_dir = project / "results" / "data"
    target = tmp_path / "external_data"
    target.mkdir()
    (target / "summary.csv").write_text("x,y\n0,1\n", encoding="utf-8")
    for path in data_dir.iterdir():
        path.unlink()
    data_dir.rmdir()
    data_dir.symlink_to(target, target_is_directory=True)

    ready = next(entry for entry in build_inventory(tmp_path) if entry.figure_id == "FigReady")

    assert ready.render_candidate is False
    assert ready.symlinked_paths == ("results/data",)


def test_build_inventory_does_not_mark_snapshot_tree_symlinks_as_candidates(tmp_path: Path) -> None:
    project = _write_project(tmp_path, "project_a")
    helper_target = tmp_path / "external_helper.py"
    helper_target.write_text("print('helper')\n", encoding="utf-8")
    (project / "hub_scripts" / "helper.py").symlink_to(helper_target)

    entries = build_inventory(tmp_path)
    ready = next(entry for entry in entries if entry.figure_id == "FigReady")

    assert ready.render_candidate is False
    assert ready.symlinked_paths == ("hub_scripts",)


def test_render_markdown_includes_workflow_and_targets(tmp_path: Path) -> None:
    _write_project(tmp_path, "project_a")

    markdown = render_markdown(build_inventory(tmp_path), title="Inventory", root=tmp_path)

    assert "`project_a`" in markdown
    assert "`FigReady`" in markdown
    assert "Symlinks" in markdown
    assert "graphhub.render_project_figure with dry_run=true" in markdown
