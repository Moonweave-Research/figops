from pathlib import Path

from scripts.gen_tool_reference import render_tool_reference

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_generated_tool_reference_matches_committed_docs():
    expected = render_tool_reference()
    actual = (HUB_ROOT / "docs" / "tools.md").read_text(encoding="utf-8")

    assert actual == expected
