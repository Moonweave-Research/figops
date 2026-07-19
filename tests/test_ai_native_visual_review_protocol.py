import re
from pathlib import Path

PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "internal"
    / "protocols"
    / "00_agent_graph_workflow.md"
)


def _protocol() -> str:
    return PROTOCOL_PATH.read_text(encoding="utf-8")


def _normalized_protocol() -> str:
    return " ".join(_protocol().casefold().split())


def _visual_loop_steps(text: str) -> list[str]:
    match = re.search(
        r"^## Visual evidence loop\s*$\n(?P<body>.*?)(?=^## )",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    assert match, "protocol must define a visual evidence loop"
    return re.findall(r"^\d+\. \*\*(.+?)\*\*", match.group("body"), flags=re.MULTILINE)


def test_protocol_orders_render_evidence_image_review_and_targeted_revision() -> None:
    steps = _visual_loop_steps(_protocol())
    assert len(steps) >= 6

    outcomes = ("render", "evidence", "preview", "inspect", "decision", "revise")
    normalized = " | ".join(step.casefold() for step in steps)
    positions = [normalized.index(outcome) for outcome in outcomes]
    assert positions == sorted(positions), "visual review outcomes must occur in causal order"


def test_protocol_requires_lazy_image_inspection_with_evidence_driven_stopping() -> None:
    text = _normalized_protocol()
    assert re.search(r"preview\s+(?:resource\s+)?only\s+when", text)
    assert re.search(r"actually inspect the image", text)
    assert re.search(r"do not infer .* from metadata alone", text)
    assert "no more than two targeted revisions" not in text
    assert re.search(r"communication goal is met, a hard blocker remains", text)
    assert "user-owned decision is required" in text
    assert "do not invent an iteration limit" in text
    assert "iteration budget is exhausted" not in text


def test_protocol_treats_unavailable_preview_as_explicit_non_visual_outcome() -> None:
    text = _normalized_protocol()
    assert re.search(r"unavailable never means passed", text)
    assert re.search(r"image was not visually reviewed", text)
    assert re.search(r"preview remains unavailable", text)
    assert re.search(r"manual_review_needed=true.*does not prevent.*inspecting the preview", text, re.DOTALL)


def test_protocol_removes_forced_render_ceremony_without_weakening_write_gates() -> None:
    text = _normalized_protocol()
    forbidden_rituals = (
        r"call `figops\.list_styles`",
        r"call `figops\.collect_artifacts` after render",
        r"do not read .*images",
        r"stop .*manual_review_needed=true.*visual judgment",
    )
    assert not any(re.search(pattern, text, re.DOTALL) for pattern in forbidden_rituals)

    assert re.search(r"non-source-mutating render does not require a dry run", text)
    assert re.search(r"unauthorized destructive mutation", text)
    assert re.search(r"fail closed when write tools are disabled", text)


def test_protocol_keeps_automatic_checks_separate_from_human_approval() -> None:
    text = _normalized_protocol()
    assert re.search(r"objective kernel evidence", text)
    assert re.search(r"explicitly selected policy", text)
    assert re.search(r"visual observations made by the agent", text)
    assert re.search(r"never describe automatic checks as human approval", text)
