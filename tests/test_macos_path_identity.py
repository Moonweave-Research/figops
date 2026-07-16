from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from hub_core.execution_project_boundary import resolve_execution_project_path
from hub_core.external_raw import verify_external_raw_materialization
from hub_core.mcp import FigOpsMCPServer
from hub_core.mcp.manifest_io import read_verified_runtime_json_object
from hub_core.path_identity import canonical_is_relative_to, canonical_paths_overlap
from hub_core.runtime_boundary import validate_runtime_location

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS root-alias regression")


def _alternate_var_spelling(path: Path) -> Path:
    text = str(path.absolute())
    if text == "/private/var" or text.startswith("/private/var/"):
        return Path(text.replace("/private/var", "/var", 1))
    if text == "/var" or text.startswith("/var/"):
        return Path(text.replace("/var", "/private/var", 1))
    pytest.skip("temporary directory is not below the macOS /var root alias")


def test_canonical_identity_treats_var_and_private_var_as_one_boundary(tmp_path: Path) -> None:
    alias = _alternate_var_spelling(tmp_path)

    assert canonical_is_relative_to(alias, tmp_path)
    assert canonical_is_relative_to(tmp_path, alias)
    assert canonical_paths_overlap(alias, tmp_path)


def test_cli_project_resolution_accepts_only_the_system_root_alias(tmp_path: Path) -> None:
    research = tmp_path / "research"
    project = research / "project"
    project.mkdir(parents=True)

    resolved = resolve_execution_project_path(
        _alternate_var_spelling(research),
        project,
    )

    assert resolved == project.resolve()


def test_runtime_disjointness_uses_identity_not_var_spelling(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    runtime = validate_runtime_location(
        _alternate_var_spelling(tmp_path / "runtime"),
        project_root=project,
    )

    assert runtime == (tmp_path / "runtime").resolve()


def test_runtime_boundary_object_keeps_the_canonical_var_identity(tmp_path: Path) -> None:
    canonical_runtime = (tmp_path / "runtime").resolve()
    alias_runtime = _alternate_var_spelling(canonical_runtime)

    runtime = validate_runtime_location(alias_runtime)

    assert runtime == canonical_runtime
    assert str(runtime).startswith("/private/var/")


def test_external_raw_verification_accepts_mixed_var_spellings(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    runtime = tmp_path / "runtime"
    allowed.mkdir()
    runtime.mkdir()
    materialized = runtime / "input.csv"
    materialized.write_bytes(b"x\n1\n")
    digest = hashlib.sha256(materialized.read_bytes()).hexdigest()
    descriptor = {
        "id": "input",
        "path": "input.csv",
        "allowed_root": "allowed",
        "version": "v1",
        "sha256": digest,
    }

    verified = verify_external_raw_materialization(
        descriptor,
        _alternate_var_spelling(materialized),
        runtime_root=runtime,
        allowed_roots={"allowed": _alternate_var_spelling(allowed)},
    )

    assert verified.materialized_path == materialized.resolve()


def test_mcp_config_and_runtime_manifest_accept_mixed_var_spellings(tmp_path: Path) -> None:
    research = tmp_path / "research"
    project = research / "project"
    runtime = tmp_path / "runtime"
    project.mkdir(parents=True)
    runtime.mkdir()
    server = FigOpsMCPServer(
        research_root=_alternate_var_spelling(research),
        runtime_root=runtime,
    )

    assert server._resolve_under_root(str(project), field_name="project_path") == project.resolve()

    manifest = runtime / "mcp_jobs" / "alias-root" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"job_id": "alias-root"}), encoding="utf-8")
    parsed = read_verified_runtime_json_object(
        _alternate_var_spelling(runtime),
        manifest,
        expected_job_id="alias-root",
    )

    assert parsed["job_id"] == "alias-root"
