import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from hub_core.claim_inventory import evaluate_project_claim_inventory

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
CLAIM_TERM_RE: Final = re.compile(
    r"\b(?:publishable|publication[- ]ready|publication readiness|journal[- ]ready)\b",
    re.IGNORECASE,
)
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
    "not journal-ready",
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
        f"{path}:{line_number}: unqualified publishable/publication-ready claim "
        f"or journal-ready claim: {line.strip()!r}. "
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


def test_authentic_journal_style_claim_does_not_permit_journal_ready_status() -> None:
    # Given: style-forward wording that tries to convert journal feel into readiness.
    text = (
        "Publication-oriented authentic journal style gives the graph a journal feel "
        "and makes it journal-ready.\n"
    )

    # When: the claim-boundary guard scans the wording.
    violations = _claim_boundary_violations(Path("README.md"), text)

    # Then: styling language still requires hard-gate evidence and manual review wording.
    assert violations
    assert "hard-gate evidence" in violations[0]
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


def test_publication_project_script_requires_verified_claim_inventory(tmp_path: Path) -> None:
    script = tmp_path / "hub_scripts" / "figures" / "plot.py"
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    selected = {
        "id": "Fig1",
        "script": script.relative_to(tmp_path).as_posix(),
        "claim_inventory": inventory.relative_to(tmp_path).as_posix(),
    }
    empty_inventory = {
        "schema_version": "figops_claim_inventory/1",
        "figure_id": "Fig1",
        "calculation_evidence_paths": [],
        "claims": [],
    }
    inventory.write_text(json.dumps(empty_inventory), encoding="utf-8")

    # A raster-producing script that displays a statistical claim contradicts
    # an empty inventory. Discovery is only a conservative blocker, never proof.
    script.write_text(
        "from PIL import Image, ImageDraw\n"
        "image = Image.new('RGB', (80, 40), 'white')\n"
        "ImageDraw.Draw(image).text((2, 2), 'p < 0.05', fill='black')\n",
        encoding="utf-8",
    )
    raster_claim = evaluate_project_claim_inventory(tmp_path, selected)
    assert raster_claim["status"] == "unverified"
    assert raster_claim["manual_review_needed"] is True
    assert raster_claim["promotion_eligible"] is False

    # An inspectable no-claim script with an explicit empty inventory is the
    # auditable no-claim publication path.
    script.write_text(
        "from PIL import Image\nImage.new('RGB', (80, 40), 'white').save('figure.png')\n",
        encoding="utf-8",
    )
    no_claim = evaluate_project_claim_inventory(tmp_path, selected)
    assert no_claim["status"] == "verified"
    assert no_claim["explicit_no_claims"] is True
    assert no_claim["promotion_eligible"] is True

    missing = evaluate_project_claim_inventory(tmp_path, {"id": "Fig1", "script": selected["script"]})
    assert missing["status"] == "unverified"
    assert missing["manual_review_needed"] is True

    script.write_bytes(b"\xff\xfe\x00")
    uninspectable = evaluate_project_claim_inventory(tmp_path, selected)
    assert uninspectable["status"] == "unverified"
    assert uninspectable["promotion_eligible"] is False


@pytest.mark.parametrize(
    ("suffix", "script_text"),
    [
        (
            ".py",
            "import matplotlib.pyplot as plt\n"
            "p = 0.0123\n"
            "fig, ax = plt.subplots()\n"
            "ax.text(0.1, 0.9, f'p={p:.3g}')\n",
        ),
        (
            ".py",
            "import matplotlib.pyplot as plt\n"
            "p_value = 0.0123\n"
            "claim_label = 'p={:.3g}'.format(p_value)\n"
            "fig, ax = plt.subplots()\n"
            "ax.annotate(claim_label, (0.1, 0.9))\n",
        ),
        (
            ".py",
            "from PIL import Image, ImageDraw\n"
            "p = 0.0123\n"
            "claim_label = 'p=' + str(p)\n"
            "image = Image.new('RGB', (80, 40), 'white')\n"
            "ImageDraw.Draw(image).text((2, 2), claim_label, fill='black')\n",
        ),
        (
            ".py",
            "def add_claim(ax, p_value_label):\n"
            "    ax.text(0.1, 0.9, p_value_label)\n",
        ),
        (
            ".py",
            "import matplotlib.pyplot as plt\n"
            "p = 0.0123\n"
            "fig, ax = plt.subplots()\n"
            "ax.set_xlabel(f'p={p:.3g}')\n",
        ),
        (
            ".py",
            "import matplotlib.pyplot as plt\n"
            "p = 0.0123\n"
            "fig, ax = plt.subplots()\n"
            "write_label = ax.text\n"
            "write_label(0.1, 0.9, f'p={p:.3g}')\n",
        ),
        (
            ".py",
            "def decorate(axis, label):\n"
            "    axis.text(0.1, 0.9, label)\n"
            "p = 0.0123\n"
            "decorate(ax, f'p={p:.3g}')\n",
        ),
        (
            ".py",
            "from local_plot_helpers import decorate\n"
            "p = 0.0123\n"
            "decorate(ax, f'p={p:.3g}')\n",
        ),
        (
            ".py",
            "import matplotlib.pyplot as plt\n"
            "p = 0.0123\n"
            "fig, ax = plt.subplots()\n"
            "ax.legend([f'p={p:.3g}'])\n",
        ),
        (
            ".R",
            "p <- 0.0123\n"
            "claim_label <- sprintf('p=%.3g', p)\n"
            "plot(1, 1)\n"
            "text(1, 1, labels = claim_label)\n",
        ),
        (
            ".R",
            "p <- 0.0123\n"
            "plot(1, 1)\n"
            "text(1, 1, paste0('p=', format(p)))\n",
        ),
        (
            ".R",
            "p <- 0.0123\n"
            "plot(1, 1)\n"
            "legend('topright', legend = sprintf('p=%.3g', p))\n",
        ),
        (
            ".R",
            "p <- 0.0123\n"
            "plot(1, 1)\n"
            "axis(1, labels = paste0('p=', p))\n",
        ),
        (
            ".R",
            "add_marker <- function(label) { text(1, 1, labels = label) }\n"
            "p <- 0.0123\n"
            "add_marker(paste0('p=', format(p)))\n",
        ),
        (
            ".R",
            "add_marker <- function(label) { text(1, 1, labels = label) }\n"
            "relay_marker <- function(message) { add_marker(message) }\n"
            "p_value <- 0.0123\n"
            "relay_marker(sprintf('p=%.3g', p_value))\n",
        ),
        (
            ".R",
            "add_marker <- function(label) { text(1, 1, labels = label) }\n"
            "marker_alias <- add_marker\n"
            "p <- 0.0123\n"
            "marker_alias(paste0('p=', p))\n",
        ),
        (
            ".R",
            "write_label <- text\n"
            "add_marker <- function(label) { write_label(1, 1, labels = label) }\n"
            "p <- 0.0123\n"
            "add_marker(paste0('p=', p))\n",
        ),
    ],
)
def test_dynamic_claim_annotations_cannot_bypass_explicit_empty_inventory(
    tmp_path: Path, suffix: str, script_text: str
) -> None:
    """Dynamic displayed claims need review even when an inventory says no claims."""

    script = tmp_path / "hub_scripts" / "figures" / f"plot{suffix}"
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    script.write_text(script_text, encoding="utf-8")
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_project_claim_inventory(
        tmp_path,
        {
            "id": "Fig1",
            "script": script.relative_to(tmp_path).as_posix(),
            "claim_inventory": inventory.relative_to(tmp_path).as_posix(),
        },
    )

    assert result["status"] == "unverified"
    assert result["manual_review_needed"] is True
    assert result["promotion_eligible"] is False
    assert result["dynamic_candidates"]
    assert "dynamic statistical-claim annotation" in result["errors"][0]


def test_constant_folded_claim_text_is_compared_with_empty_inventory(tmp_path: Path) -> None:
    script = tmp_path / "hub_scripts" / "figures" / "plot.py"
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    script.write_text(
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.text(0.1, 0.9, 'p ' + '< ' + '0.05')\n",
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_project_claim_inventory(
        tmp_path,
        {
            "id": "Fig1",
            "script": script.relative_to(tmp_path).as_posix(),
            "claim_inventory": inventory.relative_to(tmp_path).as_posix(),
        },
    )

    assert result["status"] == "unverified"
    assert result["promotion_eligible"] is False
    assert result["discovered_candidates"] == [{"source": "script_literal", "text": "p < 0.05"}]
    assert result["dynamic_candidates"] == []


def test_unrelated_dynamic_annotation_does_not_reduce_author_freedom(tmp_path: Path) -> None:
    script = tmp_path / "hub_scripts" / "figures" / "plot.py"
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    script.write_text(
        "import matplotlib.pyplot as plt\n"
        "sample_name = 'control'\n"
        "fig, ax = plt.subplots()\n"
        "ax.set_title(f'Sample: {sample_name}')\n",
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_project_claim_inventory(
        tmp_path,
        {
            "id": "Fig1",
            "script": script.relative_to(tmp_path).as_posix(),
            "claim_inventory": inventory.relative_to(tmp_path).as_posix(),
        },
    )

    assert result["status"] == "verified"
    assert result["promotion_eligible"] is True
    assert result["dynamic_candidates"] == []


def test_unrelated_dynamic_r_wrapper_annotation_does_not_reduce_author_freedom(
    tmp_path: Path,
) -> None:
    script = tmp_path / "hub_scripts" / "figures" / "plot.R"
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True)
    inventory.parent.mkdir(parents=True)
    script.write_text(
        "add_marker <- function(label) { text(1, 1, labels = label) }\n"
        "sample_id <- 'control'\n"
        "add_marker(paste0('Sample: ', sample_id))\n",
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_project_claim_inventory(
        tmp_path,
        {
            "id": "Fig1",
            "script": script.relative_to(tmp_path).as_posix(),
            "claim_inventory": inventory.relative_to(tmp_path).as_posix(),
        },
    )

    assert result["status"] == "verified"
    assert result["promotion_eligible"] is True
    assert result["dynamic_candidates"] == []
