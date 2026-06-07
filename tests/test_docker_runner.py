import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.docker_runner import DEFAULT_DOCKER_IMAGE, rerun_in_docker


def test_raises_when_docker_not_found(tmp_path):
    with patch("hub_core.docker_runner.shutil.which", return_value=None):
        try:
            rerun_in_docker(str(tmp_path), str(tmp_path), [])
            assert False, "Expected RuntimeError"
        except RuntimeError as exc:
            assert "Docker is not installed" in str(exc)


def test_filters_docker_flags_from_argv(tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result = MagicMock()
        result.returncode = 0
        return result

    with (
        patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
        patch("hub_core.docker_runner.subprocess.run", side_effect=fake_run),
    ):
        rerun_in_docker(
            str(tmp_path),
            str(tmp_path),
            ["--project", "foo", "--docker", "--docker-build"],
        )

    assert "--docker" not in captured["cmd"]
    assert "--docker-build" not in captured["cmd"]
    assert "--project" in captured["cmd"]


def test_returns_subprocess_returncode(tmp_path):
    mock_proc = MagicMock()
    mock_proc.returncode = 42

    with (
        patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
        patch("hub_core.docker_runner.subprocess.run", return_value=mock_proc),
    ):
        rc = rerun_in_docker(str(tmp_path), str(tmp_path), [])

    assert rc == 42


def test_mounts_hub_separately_when_it_is_outside_root(tmp_path):
    captured = {}
    hub_path = tmp_path / "graph-making-hub"
    root_dir = tmp_path / "ResearchOS"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result = MagicMock()
        result.returncode = 0
        return result

    with (
        patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
        patch("hub_core.docker_runner.subprocess.run", side_effect=fake_run),
    ):
        rerun_in_docker(str(hub_path), str(root_dir), [])

    assert f"{root_dir}:{root_dir}" in captured["cmd"]
    assert f"{hub_path}:{hub_path}" in captured["cmd"]


def test_uses_single_workspace_mount_when_hub_is_inside_root(tmp_path):
    captured = {}
    hub_path = tmp_path / "graph-making-hub"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result = MagicMock()
        result.returncode = 0
        return result

    with (
        patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
        patch("hub_core.docker_runner.subprocess.run", side_effect=fake_run),
    ):
        rerun_in_docker(str(hub_path), str(tmp_path), [])

    assert captured["cmd"].count("-v") == 1
    assert f"{tmp_path}:{tmp_path}" in captured["cmd"]


def test_default_image_constant():
    assert DEFAULT_DOCKER_IMAGE == "graph-making-hub:latest"


def test_timeout_returns_1(tmp_path):
    import subprocess

    with (
        patch("hub_core.docker_runner.shutil.which", return_value="/usr/bin/docker"),
        patch(
            "hub_core.docker_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=3600),
        ),
    ):
        rc = rerun_in_docker(str(tmp_path), str(tmp_path), [])

    assert rc == 1
