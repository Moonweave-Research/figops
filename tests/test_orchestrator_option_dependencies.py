from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import orchestrator


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--docker-build",), "--docker-build requires --docker"),
        (("--docker-image", "review-image:latest"), "--docker-image requires --docker"),
        (("--docker-image", "figops:latest"), "--docker-image requires --docker"),
        (("--regression-baseline", "check"), "--regression-baseline requires --check-all"),
    ],
)
def test_qualifier_without_its_mode_is_a_usage_error(extra: tuple[str, ...], message: str, capsys) -> None:
    with patch.object(sys, "argv", ["orchestrator.py", *extra]):
        with pytest.raises(SystemExit) as raised:
            orchestrator.main()

    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_docker_wraps_list_mode_instead_of_being_silently_ignored(tmp_path: Path) -> None:
    with (
        patch.object(sys, "argv", ["orchestrator.py", "--list-projects", "--docker"]),
        patch("orchestrator.get_hub_path", return_value=str(tmp_path / "hub")),
        patch("orchestrator.get_research_root", return_value=str(tmp_path)),
        patch("orchestrator.rerun_in_docker", return_value=0) as rerun,
    ):
        result = orchestrator.main()

    assert result == 0
    assert rerun.call_args.kwargs["root_dir"] == str(tmp_path)
    assert rerun.call_args.kwargs["build"] is False
