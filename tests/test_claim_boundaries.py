import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

_ROOT_INIT_MODULE: Final = "__init__"
_ROOT_INIT_PATH: Final = Path(__file__).resolve().parents[1] / "__init__.py"
if _ROOT_INIT_MODULE not in sys.modules:
    root_init_module = ModuleType(_ROOT_INIT_MODULE)
    root_init_module.__file__ = str(_ROOT_INIT_PATH)
    sys.modules[_ROOT_INIT_MODULE] = root_init_module


CLAIM_SURFACES: Final = (
    Path("README.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/internal/protocols/00_agent_graph_workflow.md"),
    Path("docs/internal/protocols/05_mcp_tool_playbook.md"),
)
RUBRIC_SURFACES: Final = (
    Path("docs/QA.md"),
    Path("docs/specs/2026-06-30-figure-quality-rubric.md"),
)
CLAIM_TERM_RE: Final = re.compile(r"\b(?:publishable|publication[- ]ready|publication readiness)\b", re.IGNORECASE)
HARD_GATE_RE: Final = re.compile(r"\b(?:hard[- ]gate|hard gates|rubric-backed|cited hard gates)\b", re.IGNORECASE)
MANUAL_REVIEW_RE: Final = re.compile(
    r"\b(?:manual_review_needed|manual-review|manual review)\b",
    re.IGNORECASE,
)
BOUNDED_NEGATIVE_PHRASES: Final = (
    "do not claim publication readiness",
    "do not claim publication-ready",
    "do not describe a graph as publication-ready",
    "must not describe a graph as publication-ready",
    "not automatically publication-ready",
    "not publication-ready",
    "not by itself a publishable verdict",
    "not sufficient for publishable",
)


def _claim_boundary_violations(path: Path, text: str) -> list[str]:
    lines = tuple(text.splitlines())
    violations: list[str] = []
    for line_index, line in enumerate(lines):
        if not CLAIM_TERM_RE.search(line):
            continue
        context = _claim_context(lines, line_index)
        if _claim_is_bounded(context):
            continue
        violations.append(_claim_violation(path, line_index + 1, line))
    return violations


def _claim_context(lines: tuple[str, ...], line_index: int) -> str:
    first_line = max(0, line_index - 1)
    last_line = min(len(lines), line_index + 3)
    return " ".join(lines[first_line:last_line]).lower()


def _claim_is_bounded(context: str) -> bool:
    if "publication-oriented" in context:
        return True
    if "unsafe:" in context:
        return True
    if "publication-ready figure quality rubric" in context:
        return True
    if "definition of \"publication-ready\"" in context and "rubric separates objective hard gates" in context:
        return True
    if "`publishable`: cited hard gates pass" in context and MANUAL_REVIEW_RE.search(context):
        return True
    if "publishable verdict" in context and ("rubric-backed" in context or "not by itself" in context):
        return True
    if "publishable claims" in context and "not sufficient" in context:
        return True
    if any(phrase in context for phrase in BOUNDED_NEGATIVE_PHRASES):
        return True
    if "requires" in context or "require" in context:
        return HARD_GATE_RE.search(context) is not None and MANUAL_REVIEW_RE.search(context) is not None
    return False


def _claim_violation(path: Path, line_number: int, line: str) -> str:
    return (
        f"{path}:{line_number}: unqualified publishable/publication-ready claim: {line.strip()!r}. "
        "Publishable claims require cited hard-gate evidence and manual_review_needed review."
    )


def _assert_no_claim_boundary_violations(paths: tuple[Path, ...]) -> None:
    violations: list[str] = []
    for path in paths:
        violations.extend(_claim_boundary_violations(path, path.read_text(encoding="utf-8")))
    assert not violations, "\n".join(violations)


def test_unqualified_publishable_claim_is_rejected() -> None:
    # Given: a synthetic public README-style overclaim.
    text = "FigOps produces publishable figures for manuscripts.\n"

    # When: the claim-boundary guard scans the wording.
    violations = _claim_boundary_violations(Path("README.md"), text)

    # Then: the guard requires both hard-gate evidence and manual review wording.
    assert violations
    assert "hard-gate evidence" in violations[0]
    assert "manual_review_needed" in violations[0]


def test_publication_ready_marketing_claim_is_rejected() -> None:
    # Given: a marketing-style public claim without rubric evidence.
    text = "FigOps turns CSVs into publication-ready figures automatically.\n"

    # When: the claim-boundary guard scans the wording.
    violations = _claim_boundary_violations(Path("README.md"), text)

    # Then: the wording is blocked until evidence and review limits are named.
    assert violations
    assert "publication-ready claim" in violations[0]
    assert "hard-gate evidence" in violations[0]


def test_manual_review_needed_false_overclaim_is_rejected() -> None:
    # Given: a synthetic claim that treats the render envelope as a publishable verdict.
    text = "`manual_review_needed=false` is sufficient for a publishable claim.\n"

    # When: the claim-boundary guard scans the wording.
    violations = _claim_boundary_violations(Path("docs/ROADMAP.md"), text)

    # Then: manual-review status alone is rejected as a publication claim boundary.
    assert violations
    assert "manual_review_needed" in violations[0]


def test_rubric_publishable_verdict_definition_is_allowed() -> None:
    # Given: the rubric's bounded verdict definition.
    text = "- `publishable`: cited hard gates pass, `manual_review_needed` is not true, and advisories pass.\n"

    # When: the claim-boundary guard scans the rubric wording.
    violations = _claim_boundary_violations(Path("docs/QA.md"), text)

    # Then: rubric verdict definitions are not treated as marketing overclaims.
    assert not violations


def test_claim_boundary_docs_keep_public_wording_bounded() -> None:
    # Given: the scoped README, roadmap, and protocol wording surfaces.
    paths = CLAIM_SURFACES

    # When / Then: every claim term in those docs stays explicitly bounded.
    _assert_no_claim_boundary_violations(paths)


def test_rubric_docs_keep_publishable_verdict_definitions_bounded() -> None:
    # Given: rubric docs that are allowed to define publication verdicts.
    paths = RUBRIC_SURFACES

    # When / Then: verdict definitions and unsafe examples do not create false positives.
    _assert_no_claim_boundary_violations(paths)


def test_publication_oriented_readme_wording_is_preserved() -> None:
    # Given: the current public README.
    text = Path("README.md").read_text(encoding="utf-8")

    # When: the guard checks the public claim surface.
    violations = _claim_boundary_violations(Path("README.md"), text)

    # Then: publication-oriented wording remains allowed and unqualified claims stay absent.
    assert "publication-oriented" in text
    assert not violations
