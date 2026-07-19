from pathlib import Path

from scripts.gen_tool_reference import PROFILE_TOOL_DOCS, render_tool_reference

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_generated_tool_reference_matches_committed_docs():
    expected = render_tool_reference()
    actual = (HUB_ROOT / "docs" / "tools.md").read_text(encoding="utf-8")

    assert actual == expected


def test_generated_profile_references_match_committed_docs():
    for profile, path in PROFILE_TOOL_DOCS.items():
        assert path.read_text(encoding="utf-8") == render_tool_reference(profile)


def test_generated_references_do_not_invent_statistical_results() -> None:
    references = [
        render_tool_reference(),
        render_tool_reference("v2"),
        render_tool_reference("compatibility"),
    ]
    invented_example_fragments = (
        '"aggregate": "mean"',
        '"bar_error_column": "sem"',
        '"label": "p<0.05"',
        '"confidence_level": 0.95',
    )

    assert all(
        fragment not in reference
        for reference in references
        for fragment in invented_example_fragments
    )
