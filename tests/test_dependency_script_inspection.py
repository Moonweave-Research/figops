from __future__ import annotations

from pathlib import Path

import pytest

from hub_core.dependency_script_inspection import analyze_dependency_script


def test_python_imports_and_path_literals_are_explicit_candidates() -> None:
    result = analyze_dependency_script(
        "import pandas as pd\n"
        "from pathlib import Path\n"
        "frame = pd.read_csv(\"data/input.csv\")\n",
        ".py",
    )

    assert result["inspectable"] is True
    assert result["dependency_scan_incomplete"] is False
    candidates = result["static_candidates"]
    assert any(item["kind"] == "import" and item["path"] == "pandas" for item in candidates)
    assert any(item["kind"] == "import" and item["path"] == "pathlib" for item in candidates)
    assert [item["path"] for item in candidates if item["kind"] == "path_literal"] == ["data/input.csv"]
    assert result["hardcoded_unresolved_references"]


def test_r_source_and_read_calls_are_explicit_candidates() -> None:
    result = analyze_dependency_script(
        'source("scripts/helper.R")\n'
        'values <- read.csv("data/input.csv")\n',
        ".r",
    )

    assert result["inspectable"] is True
    assert result["dependency_scan_incomplete"] is False
    assert [item["path"] for item in result["static_candidates"]] == [
        "scripts/helper.R",
        "data/input.csv",
    ]
    assert len(result["hardcoded_unresolved_references"]) == 2


def test_suffixless_python_path_api_literals_are_candidates() -> None:
    result = analyze_dependency_script(
        "from pathlib import Path\n"
        "frame = read_csv('input')\n"
        "path = Path('workspace')\n"
        "handle = open('README')\n",
        ".py",
    )

    assert result["dependency_scan_incomplete"] is False
    assert {item["path"] for item in result["static_candidates"] if item["kind"] == "path_literal"} == {
        "input",
        "workspace",
        "README",
    }

    wrapped = analyze_dependency_script("handle = open(Path('wrapped'))", ".py")
    assert wrapped["dependency_scan_incomplete"] is False
    assert [item["path"] for item in wrapped["static_candidates"] if item["kind"] == "path_literal"] == [
        "wrapped"
    ]

    content = analyze_dependency_script("Path('output').write_text(content_value)", ".py")
    assert content["dependency_scan_incomplete"] is False
    assert [item["path"] for item in content["static_candidates"] if item["kind"] == "path_literal"] == [
        "output"
    ]

    assigned = analyze_dependency_script("input_path = Path('assigned')\nread_csv(input_path)", ".py")
    assert assigned["dependency_scan_incomplete"] is False
    assert [item["path"] for item in assigned["static_candidates"] if item["kind"] == "path_literal"] == [
        "assigned"
    ]


def test_suffixless_r_read_and_source_literals_are_candidates() -> None:
    result = analyze_dependency_script(
        'source("helper")\n'
        'values <- read.csv("input")\n',
        ".r",
    )

    assert result["inspectable"] is True
    assert result["dependency_scan_incomplete"] is False
    assert [item["path"] for item in result["static_candidates"]] == ["helper", "input"]
    assert len(result["hardcoded_unresolved_references"]) == 2


def test_python_path_keyword_variants_remain_unresolved_when_dynamic() -> None:
    result = analyze_dependency_script(
        "frame = read_csv(filepath_or_buffer=input_path)\n",
        ".py",
    )

    assert result["dependency_scan_incomplete"] is True
    assert result["static_candidates"] == []
    assert result["hardcoded_unresolved_references"][0]["kind"] == "dynamic_path"


def test_python_syntax_failure_fails_closed() -> None:
    result = analyze_dependency_script("if True print('broken')", ".py")

    assert result["inspectable"] is False
    assert result["dependency_scan_incomplete"] is True
    assert result["static_candidates"] == []
    assert result["hardcoded_unresolved_references"][0]["kind"] == "parse_error"


def test_r_unbalanced_call_fails_closed() -> None:
    result = analyze_dependency_script('values <- read.csv("data/input.csv"', ".r")

    assert result["inspectable"] is False
    assert result["dependency_scan_incomplete"] is True
    assert result["static_candidates"] == []
    assert result["hardcoded_unresolved_references"][0]["kind"] == "parse_error"


def test_dynamic_path_is_incomplete_and_unresolved() -> None:
    result = analyze_dependency_script("frame = read_csv(input_path)", ".py")

    assert result["inspectable"] is True
    assert result["dependency_scan_incomplete"] is True
    assert result["static_candidates"] == []
    assert result["hardcoded_unresolved_references"][0]["kind"] == "dynamic_path"


def test_unmapped_path_is_not_assigned_a_guessed_role() -> None:
    result = analyze_dependency_script('frame = read_csv("data/input.csv")', ".py")

    unresolved = result["hardcoded_unresolved_references"]
    assert len(unresolved) == 1
    assert unresolved[0]["kind"] == "hardcoded_path"
    assert "role mapping" in unresolved[0]["reason"]


def test_explicit_role_root_can_resolve_a_literal_without_guessing() -> None:
    result = analyze_dependency_script(
        'frame = read_csv("raw/input.csv")',
        ".py",
        role_roots={"raw": "raw"},
    )

    assert result["static_candidates"][0]["path"] == "raw/input.csv"
    assert result["hardcoded_unresolved_references"] == []


def test_nested_role_roots_resolve_only_the_terminal_declared_role() -> None:
    result = analyze_dependency_script(
        'frame = read_csv("hub_scripts/analysis/input")',
        ".py",
        role_roots={
            "scripts": "hub_scripts",
            "analysis_scripts": "hub_scripts/analysis",
        },
    )

    assert result["hardcoded_unresolved_references"] == []


def test_aggregate_role_root_does_not_clear_a_dependency() -> None:
    result = analyze_dependency_script(
        'frame = read_csv("hub_scripts/input")',
        ".py",
        role_roots={"scripts": "hub_scripts"},
    )

    assert result["hardcoded_unresolved_references"][0]["kind"] == "hardcoded_path"


@pytest.mark.parametrize(
    ("suffix", "source"),
    [
        (".py", "frame = read_csv('https://example.test/input.csv')"),
        (".r", 'frame <- read.csv("https://example.test/input.csv")'),
    ],
)
def test_remote_path_literals_remain_fail_closed(suffix: str, source: str) -> None:
    result = analyze_dependency_script(source, suffix)

    assert result["dependency_scan_incomplete"] is True
    assert result["static_candidates"] == []
    assert result["hardcoded_unresolved_references"][0]["kind"] == "external_path"


def test_result_is_deterministic() -> None:
    source = 'b = read_csv("b.csv")\na = read_csv("a.csv")\n'

    assert analyze_dependency_script(source, ".py") == analyze_dependency_script(source, ".py")


def test_unresolved_scanner_output_can_be_handed_to_apply_gate(tmp_path: Path) -> None:
    from hub_core.structure_apply import apply_structure_plan
    from hub_core.structure_plan import build_structure_plan, confirmation_token

    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_text("x\n1\n", encoding="utf-8")
    evidence = analyze_dependency_script('frame = read_csv("legacy/input.csv")', ".py")
    plan = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
        hardcoded_unresolved_references=evidence["hardcoded_unresolved_references"],
    )

    with pytest.raises(RuntimeError, match="hard-coded"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))
