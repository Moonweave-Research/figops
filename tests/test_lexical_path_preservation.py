from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from hub_core.athena_bridge import AthenaBridge, RenderManifest
from hub_core.config_parser import find_config_path
from hub_core.process_runner_inputs import prefetch_and_revalidate_inputs
from hub_core.runtime_boundary import validate_runtime_location
from hub_core.runtime_paths import preview_runtime_root


def test_runtime_validation_returns_canonical_identity_when_input_uses_alias(tmp_path: Path) -> None:
    lexical = (tmp_path / "alias" / "runtime").absolute()
    canonical = (tmp_path / "canonical" / "runtime").absolute()

    with patch("hub_core.runtime_boundary._resolved", return_value=canonical):
        returned = validate_runtime_location(lexical)

    assert returned == canonical


def test_runtime_preview_returns_canonical_identity_without_creating_alias_target(
    tmp_path: Path,
) -> None:
    lexical = (tmp_path / "alias" / "runtime").absolute()
    canonical = (tmp_path / "canonical" / "runtime").absolute()

    with (
        patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(lexical)}, clear=False),
        patch("hub_core.runtime_boundary._resolved", return_value=canonical),
    ):
        returned = Path(preview_runtime_root())

    assert returned == canonical
    assert not lexical.exists()
    assert not canonical.exists()


def test_runtime_preview_preserves_only_a_verified_macos_system_alias(
    tmp_path: Path,
) -> None:
    lexical = (tmp_path / "alias" / "runtime").absolute()
    canonical = (tmp_path / "canonical" / "runtime").absolute()

    with (
        patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(lexical)}, clear=False),
        patch("hub_core.runtime_boundary._resolved", return_value=canonical),
        patch("hub_core.runtime_paths._is_verified_macos_alias_path", return_value=True),
    ):
        returned = preview_runtime_root()

    assert returned == str(lexical)
    assert not lexical.exists()
    assert not canonical.exists()


def test_config_discovery_validates_canonical_candidate_but_returns_lexical_path(
    tmp_path: Path,
) -> None:
    project = (tmp_path / "alias-project").absolute()
    project.mkdir()
    expected = project / "project_config.yaml"
    expected.write_text("project:\n  name: lexical\n", encoding="utf-8")
    canonical_candidate = MagicMock()
    canonical_candidate.exists.return_value = True

    with patch(
        "hub_core.config_parser.resolve_project_input",
        return_value=canonical_candidate,
    ) as resolver:
        returned = find_config_path(project)

    assert returned == str(expected)
    resolver.assert_called_once()


def test_prefetch_and_environment_inputs_preserve_lexical_project_root(
    tmp_path: Path,
) -> None:
    project = (tmp_path / "alias-project").absolute()
    project.mkdir()
    lexical_input = project / "input.csv"
    lexical_input.write_text("x\n1\n", encoding="utf-8")
    canonical_input = (tmp_path / "canonical-project" / "input.csv").absolute()
    prefetcher = MagicMock()
    snapshot = MagicMock()
    snapshot.path = canonical_input

    with (
        patch(
            "hub_core.process_runner_inputs.resolve_project_input",
            return_value=canonical_input,
        ),
        patch(
            "hub_core.process_runner_inputs.snapshot_project_input",
            return_value=snapshot,
        ),
        patch(
            "hub_core.process_runner_inputs.revalidate_project_input",
            return_value=canonical_input,
        ),
        patch(
            "hub_core.process_runner_inputs.canonical_path",
            return_value=canonical_input,
        ),
    ):
        returned = prefetch_and_revalidate_inputs(project, ["input.csv"], prefetcher)

    prefetcher.ensure_local.assert_called_once_with([str(lexical_input)])
    assert returned == [lexical_input]


def test_athena_manifest_uses_lexical_runtime_path_but_canonical_output_identity(
    tmp_path: Path,
) -> None:
    project = (tmp_path / "alias-project").absolute()
    output = project / "results" / "figures" / "figure.png"
    runtime = (tmp_path / "alias-runtime").absolute()
    canonical_output = (tmp_path / "canonical-project" / "results" / "figures" / "figure.png").absolute()
    manifest = RenderManifest()

    with (
        patch.dict(os.environ, {"PROJECT_ROOT": str(project)}, clear=False),
        patch("hub_core.athena_bridge.canonical_is_relative_to", return_value=True),
        patch("hub_core.athena_bridge.canonical_path", return_value=canonical_output),
        patch(
            "hub_core.athena_bridge.resolve_diagnostics_dir",
            return_value=str(runtime / "diagnostics"),
        ),
    ):
        returned = Path(AthenaBridge()._write_manifest(str(output), manifest))

    assert returned.is_relative_to(runtime)
    assert str(project) not in str(returned)
