from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_public_beta_readme_has_copy_paste_entrypoints() -> None:
    readme = (HUB_ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.startswith("# FigOps\n")
    assert "MCP-native figure operations" in readme
    assert "docs/quickstart.md" in readme
    assert "docs/mcp_setup.md" in readme
    assert "docs/positioning.md" in readme
    assert "uv run python graphhub_mcp_server.py --smoke" in readme
    assert "uv run python orchestrator.py --project examples/synthetic_project --step plot --force" in readme


def test_public_beta_docs_link_the_local_setup_path() -> None:
    quickstart = (HUB_ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    onboarding = (HUB_ROOT / "docs" / "onboarding.md").read_text(encoding="utf-8")
    mcp_setup = (HUB_ROOT / "docs" / "mcp_setup.md").read_text(encoding="utf-8")
    positioning = (HUB_ROOT / "docs" / "positioning.md").read_text(encoding="utf-8")

    assert "uv sync" in quickstart
    assert "uv run python graphhub_mcp_server.py --smoke" in quickstart
    assert "examples/synthetic_project" in quickstart
    assert "mcp_setup.md" in onboarding
    assert "graphhub_mcp_server.py" in mcp_setup
    assert "write tools default to disabled" in mcp_setup
    assert "generic plotting MCP" in positioning
    assert "figure recipe tools" in positioning


def test_public_beta_examples_are_copy_paste_runnable() -> None:
    examples = {
        "synthetic_project": "uv run python orchestrator.py --project examples/synthetic_project --step plot --force",
        "multipanel_project": "uv run python orchestrator.py --project examples/multipanel_project --step plot --force",
        "materials_polymer_recipe": (
            "uv run python orchestrator.py --project examples/materials_polymer_recipe --step all --force"
        ),
    }

    for name, command in examples.items():
        readme = (HUB_ROOT / "examples" / name / "README.md").read_text(encoding="utf-8")

        assert "public-safe" in readme
        assert "From the repository root" in readme
        assert command in readme
        assert "Expected output" in readme or "Expected Output" in readme


def test_public_beta_local_gate_is_documented() -> None:
    contributing = (HUB_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    qa = (HUB_ROOT / "docs" / "QA.md").read_text(encoding="utf-8")

    for command in (
        "uv run python scripts/check_public_release.py",
        "uv run python graphhub_mcp_server.py --smoke",
        "uv run python scripts/gen_tool_reference.py --check",
        "uv run python -m pytest -q",
    ):
        assert command in contributing
        assert command in qa
