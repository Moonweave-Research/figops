from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hub_core.canonical_docs import canonical_docs_registry
from hub_core.config_parser import validate_config
from hub_core.data_contract import validate_data_contract, validate_data_contract_preflight
from hub_core.data_contract_io import _read_hdf_path, _read_hdf_verified_stream, read_project_data_safe
from hub_core.mcp import GraphHubMCPServer
from hub_core.project_paths import (
    ProjectPathError,
    normalize_project_relative_path,
    resolve_project_input,
    resolve_project_output,
    revalidate_project_input,
    snapshot_project_input,
)
from tests._symlink import symlink_or_skip


@pytest.mark.parametrize(
    "declaration",
    [
        "/etc/passwd",
        "C:\\outside.csv",
        "C:/outside.csv",
        "C:drive-relative.csv",
        "\\rooted\\outside.csv",
        "\\\\server\\share\\outside.csv",
        "//server/share/outside.csv",
        "\\\\?\\C:\\outside.csv",
        "\\\\.\\PhysicalDrive0",
    ],
)
def test_declaration_rejects_posix_windows_drive_unc_and_device_paths(declaration: str) -> None:
    with pytest.raises(ProjectPathError, match="project-relative|drive|UNC"):
        normalize_project_relative_path(declaration, purpose="data_contract.csv_checks[1].path")


@pytest.mark.parametrize(
    "declaration",
    ["../outside.csv", "nested/../../outside.csv", "nested\\..\\outside.csv", "nested/..\\outside.csv"],
)
def test_declaration_rejects_mixed_separator_traversal(declaration: str) -> None:
    with pytest.raises(ProjectPathError, match="traversal"):
        normalize_project_relative_path(declaration)


@pytest.mark.parametrize("declaration", ["NUL", "con.txt", "nested/COM1.csv", "aux. ", "LPT9"])
def test_declaration_rejects_reserved_windows_device_names(declaration: str) -> None:
    with pytest.raises(ProjectPathError, match="reserved Windows device"):
        normalize_project_relative_path(declaration)


def test_resolve_project_input_accepts_nested_regular_file(tmp_path: Path) -> None:
    nested = tmp_path / "results" / "data"
    nested.mkdir(parents=True)
    data = nested / "summary.csv"
    data.write_text("x,y\n1,2\n", encoding="utf-8")

    resolved = resolve_project_input(tmp_path, "results\\data/summary.csv")

    assert resolved == data.resolve()


def test_resolve_project_input_rejects_missing_and_directory(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    directory.mkdir()

    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_project_input(tmp_path, "missing.csv")
    with pytest.raises(ProjectPathError, match="regular file"):
        resolve_project_input(tmp_path, "data")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is not supported on this platform")
def test_resolve_project_input_rejects_fifo(tmp_path: Path) -> None:
    fifo = tmp_path / "input.fifo"
    os.mkfifo(fifo)

    with pytest.raises(ProjectPathError, match="regular file"):
        resolve_project_input(tmp_path, "input.fifo")


def test_resolve_project_input_rejects_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("x\n1\n", encoding="utf-8")
    symlink_or_skip(project / "input.csv", outside)

    with pytest.raises(ProjectPathError, match="escapes the project root"):
        resolve_project_input(project, "input.csv")


def test_resolve_project_output_rejects_symlinked_parent_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    symlink_or_skip(project / "results", outside, target_is_directory=True)

    with pytest.raises(ProjectPathError, match="escapes the project root"):
        resolve_project_output(project, "results/figure.png")


def test_revalidate_project_input_detects_identity_change(tmp_path: Path) -> None:
    data = tmp_path / "input.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    snapshot = snapshot_project_input(tmp_path, "input.csv")
    replacement = tmp_path / "replacement.csv"
    replacement.write_text("x\n2\n", encoding="utf-8")
    data.unlink()
    replacement.replace(data)

    with pytest.raises(ProjectPathError, match="changed after validation"):
        revalidate_project_input(tmp_path, "input.csv", expected_snapshot=snapshot)


def test_config_rejects_cross_platform_unsafe_data_script_and_output_paths() -> None:
    config = {
        "project": {"name": "Unsafe paths"},
        "visual_style": {"target_format": "nature"},
        "data_contract": {"csv_checks": [{"path": "C:\\outside.csv"}]},
        "figures": [{"id": "Fig1", "script": "..\\plot.py", "output": "//server/share/Fig1.png"}],
    }

    errors = validate_config(config)

    combined = " ".join(errors)
    assert "data_contract.csv_checks[1].path" in combined
    assert "figures[1].script" in combined
    assert "figures[1].output" in combined


def test_preflight_rejects_before_prefetch(tmp_path: Path) -> None:
    prefetcher = Mock()
    config = {"data_contract": {"csv_checks": [{"path": "../outside.csv"}]}}

    assert not validate_data_contract_preflight(tmp_path, config, require_existing=True, prefetcher=prefetcher)
    prefetcher.ensure_local.assert_not_called()


def test_data_contract_prefetches_and_reads_contained_input_once(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    config = {"data_contract": {"csv_checks": [{"path": "data.csv"}]}}
    prefetcher = Mock()

    class Frame:
        columns: list[str] = []

        def __len__(self) -> int:
            return 1

    with (
        patch("hub_core.data_contract_io.read_data_safe", return_value=Frame()) as read_data,
        patch(
            "hub_core.data_contract._check_statistical_quality",
            return_value={"quality_passed": True},
        ),
    ):
        assert validate_data_contract(tmp_path, config, prefetcher=prefetcher, write_sidecar=False)

    prefetcher.ensure_local.assert_called_once_with([str(data.resolve())])
    read_data.assert_called_once()


def test_read_project_data_revalidates_identity_before_reader(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    snapshot = snapshot_project_input(tmp_path, "data.csv")
    replacement = tmp_path / "replacement.csv"
    replacement.write_text("x\n2\n", encoding="utf-8")
    data.unlink()
    replacement.replace(data)
    reader = Mock(side_effect=AssertionError("reader must not run"))

    with patch("hub_core.data_contract_io.read_data_safe", reader):
        with pytest.raises(ProjectPathError, match="changed after validation"):
            read_project_data_safe(tmp_path, "data.csv", object(), expected_snapshot=snapshot)
    reader.assert_not_called()


def test_verified_handle_never_reopens_swapped_parent_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    data = data_dir / "input.csv"
    data.write_text("SAFE_CONTENT", encoding="utf-8")
    snapshot = snapshot_project_input(project, "data/input.csv")
    displaced = project / "data-original"
    observed: list[bytes] = []

    def swap_parent_then_read_handle(source, _pd, **_kwargs):
        try:
            data_dir.rename(displaced)
        except PermissionError as exc:
            # Windows may deny the directory swap while the verified descriptor
            # is open. That is already fail-closed; prove the held bytes are the
            # safe source and surface a stable security failure to the caller.
            observed.append(source.read())
            raise ProjectPathError("parent directory swap was denied while the input handle was open") from exc
        data_dir.mkdir()
        (data_dir / "input.csv").write_text("OUTSIDE_SECRET", encoding="utf-8")
        observed.append(source.read())
        return object()

    with patch("hub_core.data_contract_io.read_data_safe", side_effect=swap_parent_then_read_handle):
        with pytest.raises(ProjectPathError, match="changed after validation|swap was denied"):
            read_project_data_safe(
                project,
                "data/input.csv",
                object(),
                expected_snapshot=snapshot,
            )

    assert observed == [b"SAFE_CONTENT"]
    assert b"OUTSIDE_SECRET" not in observed


def test_unsafe_declaration_error_does_not_echo_external_path() -> None:
    secret = r"C:\Users\operator\secret-root\secret.csv"

    with pytest.raises(ProjectPathError) as captured:
        normalize_project_relative_path(secret, purpose="data_contract.csv_checks[1].path")

    assert secret not in str(captured.value)
    assert "secret-root" not in str(captured.value)


def test_mcp_project_contract_error_does_not_disclose_absolute_declaration(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    project = research_root / "project"
    project.mkdir(parents=True)
    secret_root = tmp_path / "allowed-secret"
    secret_root.mkdir()
    secret = secret_root / "secret.csv"
    secret.write_text("secret\nOUTSIDE_SECRET\n", encoding="utf-8")
    (project / "project_config.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  name: Redaction witness",
                "visual_style:",
                "  target_format: nature",
                "data_contract:",
                "  csv_checks:",
                f"    - path: {json.dumps(str(secret))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    server = GraphHubMCPServer(
        config={"allowed_data_roots": [str(secret_root)], "write_tools_enabled": True},
        research_root=research_root,
        runtime_root=tmp_path / "runtime",
    )

    result = server.call_tool(
        "figops.render_project_figure",
        {"project_path": "project", "job_id": "redaction-witness", "dry_run": True},
    )["structuredContent"]

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["status"] == "error"
    assert str(secret) not in serialized
    assert "allowed-secret" not in serialized


def test_diagnostic_redaction_does_not_replace_project_inside_project_relative(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    research_root.mkdir()
    server = GraphHubMCPServer(research_root=research_root, runtime_root=tmp_path / "runtime")

    sanitized = server._sanitize_diagnostic_text(
        "field must be a project-relative path",
        {"project_path": "project"},
    )

    assert sanitized == "field must be a project-relative path"


def test_hdf_empty_dataset_error_does_not_disclose_materialized_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_temp_path = tmp_path / "figops_verified_hdf_secret_marker" / "input.h5"

    class FakePandas:
        @staticmethod
        def read_hdf(_path, *, key):
            raise KeyError(key)

    class EmptyHdf:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def keys():
            return []

    monkeypatch.setitem(sys.modules, "h5py", SimpleNamespace(File=lambda *_args, **_kwargs: EmptyHdf()))

    with pytest.raises(KeyError) as captured:
        _read_hdf_path(secret_temp_path, FakePandas(), "/data")

    assert str(secret_temp_path) not in str(captured.value)
    assert "secret_marker" not in str(captured.value)


def test_hdf_materialization_redacts_temp_path_from_parser_exception() -> None:
    def corrupt_parser(path, _pd, _key):
        raise ValueError(f"corrupt HDF5 file at {path}")

    with patch("hub_core.data_contract_io._read_hdf_path", side_effect=corrupt_parser):
        with pytest.raises(ValueError) as captured:
            _read_hdf_verified_stream(io.BytesIO(b"not-hdf"), object(), "/data")

    message = str(captured.value)
    assert "figops_verified_hdf_" not in message
    assert "<verified-hdf-input>" in message


def test_prefetch_boundary_change_fails_before_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    outside = tmp_path / "outside.csv"
    outside.write_text("x\n2\n", encoding="utf-8")
    config = {"data_contract": {"csv_checks": [{"path": "data.csv"}]}}

    class EscapingPrefetcher:
        def ensure_local(self, _paths: list[str]) -> None:
            data.unlink()
            symlink_or_skip(data, outside)

    with patch("hub_core.data_contract._read_project_data_safe") as reader:
        assert not validate_data_contract(
            project,
            config,
            prefetcher=EscapingPrefetcher(),
            write_sidecar=False,
        )
    reader.assert_not_called()


def test_canonical_docs_registry_requires_contained_non_symlink_regular_file(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    ready = docs / "ready.md"
    ready.write_text("# Ready\n", encoding="utf-8")
    target = docs / "target.md"
    target.write_text("# Target\n", encoding="utf-8")
    symlink_or_skip(docs / "linked.md", target)
    (docs / "directory.md").mkdir()
    config = {
        "project": {"name": "Docs"},
        "canonical_docs": [
            "docs/ready.md",
            "docs/linked.md",
            "docs/directory.md",
            "../outside.md",
        ],
    }

    registry = canonical_docs_registry(tmp_path, config)

    by_path = {item["path"]: item for item in registry["docs"]}
    assert by_path["docs/ready.md"]["exists"] is True
    assert by_path["docs/ready.md"]["regular_file"] is True
    assert by_path["docs/ready.md"]["symlinked"] is False
    assert by_path["docs/linked.md"]["exists"] is False
    assert by_path["docs/linked.md"]["symlinked"] is True
    assert by_path["docs/directory.md"]["exists"] is False
    assert by_path["../outside.md"]["contained"] is False
