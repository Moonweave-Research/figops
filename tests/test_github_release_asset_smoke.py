import json
from pathlib import Path

from scripts.github_release_asset_smoke import (
    expected_asset_names,
    gh_release_view_command,
    inspect_release_assets,
    release_tag,
)


def _write_pyproject(root: Path, version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(f'[project]\nname = "graph-making-hub"\nversion = "{version}"\n')


def _write_fake_gh(path: Path, payload: dict[str, object], returncode: int = 0) -> None:
    if returncode == 0:
        body = f"print({json.dumps(json.dumps(payload))})"
    else:
        body = "import sys; print('boom', file=sys.stderr); sys.exit(1)"
    path.write_text(f"#!/usr/bin/env python3\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_expected_release_asset_names_use_current_version(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "1.2.3")

    assert release_tag(tmp_path) == "v1.2.3"
    assert expected_asset_names(tmp_path) == (
        "graph_making_hub-1.2.3-py3-none-any.whl",
        "graph_making_hub-1.2.3.tar.gz",
    )


def test_gh_release_view_command_targets_assets_json() -> None:
    assert gh_release_view_command("gh-test", "owner/repo", "v1.2.3") == (
        "gh-test",
        "release",
        "view",
        "v1.2.3",
        "--repo",
        "owner/repo",
        "--json",
        "assets,url,tagName",
    )


def test_inspect_release_assets_accepts_expected_assets(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "1.2.3")
    fake_gh = tmp_path / "fake-gh"
    _write_fake_gh(
        fake_gh,
        {
            "url": "https://example.test/release",
            "tagName": "v1.2.3",
            "assets": [
                {"name": "graph_making_hub-1.2.3-py3-none-any.whl"},
                {"name": "graph_making_hub-1.2.3.tar.gz"},
            ],
        },
    )

    result = inspect_release_assets(tmp_path, repo="owner/repo", gh_bin=str(fake_gh))

    assert result["ok"]
    assert result["url"] == "https://example.test/release"


def test_inspect_release_assets_blocks_missing_wheel(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "1.2.3")
    fake_gh = tmp_path / "fake-gh"
    _write_fake_gh(fake_gh, {"url": "", "tagName": "v1.2.3", "assets": []})

    result = inspect_release_assets(tmp_path, repo="owner/repo", gh_bin=str(fake_gh))

    assert not result["ok"]
    assert any("graph_making_hub-1.2.3-py3-none-any.whl" in blocker for blocker in result["blockers"])
