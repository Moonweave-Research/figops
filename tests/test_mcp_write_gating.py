from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub_core.human_review_receipt import (
    build_review_subject,
    canonical_human_review_receipt_bytes,
    opaque_figure_artifact_id,
    opaque_project_id,
)
from hub_core.mcp import FigOpsMCPServer
from hub_core.promotion_gate_recording import (
    PromotionGateRecordingError,
    discard_promotion_gate_receipt,
    record_promotion_gate_receipt,
)
from tests.human_review_receipt_helpers import receipt
from tests.test_mcp_rendering import _write_project_render_fixture
from tests.test_result_promotion_integration import _gate_receipt


def _review(project_name: str = "Project Render Fixture", figure_id: str = "Fig1") -> dict[str, object]:
    subject = build_review_subject(
        project_id=opaque_project_id(project_name),
        artifact_id=opaque_figure_artifact_id(figure_id),
        artifact_sha256="1" * 64,
        lineage_receipt_sha256="2" * 64,
        evidence_digest="3" * 64,
        resolved_policy_digest="4" * 64,
        decision_scope="figure_scientific_and_communication",
    )
    return receipt(subject=subject)


def _server(root: Path, *, writes: bool) -> FigOpsMCPServer:
    return FigOpsMCPServer(
        research_root=root,
        runtime_root=root / "runtime",
        write_tools_enabled=writes,
    )


def _arguments(
    project: Path,
    review: dict[str, object],
    *,
    figure_id: str = "Fig1",
    **extra: object,
) -> dict[str, object]:
    return {
        "project_path": str(project),
        "figure_id": figure_id,
        "relative_path": "human/review.json",
        "review_receipt": review,
        **extra,
    }


def test_review_writer_is_write_gated_and_not_discovered_by_frozen_profiles(tmp_path: Path) -> None:
    project = _write_project_render_fixture(tmp_path)
    review = _review()
    disabled = _server(tmp_path, writes=False)

    response = disabled.call_tool("figops.record_human_review", _arguments(project, review))
    assert response["isError"] is True
    assert response["structuredContent"]["error_category"] == "disabled"
    assert not (project / "results" / "evidence").exists()
    assert "figops.record_human_review" not in {
        item["name"] for item in disabled.list_tool_definitions()
    }


def test_enabled_review_writer_records_exact_canonical_bytes_and_binds_subject(tmp_path: Path) -> None:
    project = _write_project_render_fixture(tmp_path)
    review = _review()
    server = _server(tmp_path, writes=True)

    response = server.call_tool("figops.record_human_review", _arguments(project, review))
    result = response["structuredContent"]
    destination = project / "results" / "evidence" / "human" / "review.json"
    assert response["isError"] is False
    assert result["receipt_id"] == review["receipt_id"]
    assert destination.read_bytes() == canonical_human_review_receipt_bytes(review)


def test_review_writer_rejects_subject_mismatch_without_creating_evidence(tmp_path: Path) -> None:
    project = _write_project_render_fixture(tmp_path)
    server = _server(tmp_path, writes=True)

    wrong_project = server.call_tool(
        "figops.record_human_review", _arguments(project, _review("Other Project"))
    )
    wrong_artifact = server.call_tool(
        "figops.record_human_review", _arguments(project, _review(figure_id="OtherFigure"))
    )
    unconfigured_figure = server.call_tool(
        "figops.record_human_review",
        _arguments(project, _review(figure_id="OtherFigure"), figure_id="OtherFigure"),
    )
    assert wrong_project["isError"] is True
    assert wrong_artifact["isError"] is True
    assert unconfigured_figure["isError"] is True
    assert not (project / "results" / "evidence").exists()


def test_review_writer_rejects_escape_self_described_authority_and_no_clobber(tmp_path: Path) -> None:
    project = _write_project_render_fixture(tmp_path)
    server = _server(tmp_path, writes=True)
    review = _review()

    escaped = server.call_tool(
        "figops.record_human_review", _arguments(project, review, relative_path="../outside.json")
    )
    backslash = server.call_tool(
        "figops.record_human_review", _arguments(project, review, relative_path="human\\review.json")
    )
    forged = server.call_tool(
        "figops.record_human_review", _arguments(project, review, approval={"approved": True})
    )
    assert escaped["isError"] is True
    assert backslash["isError"] is True
    assert forged["isError"] is True
    assert not (tmp_path / "outside.json").exists()

    destination = project / "results" / "evidence" / "human" / "review.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"winner")
    raced = server.call_tool("figops.record_human_review", _arguments(project, review))
    assert raced["isError"] is True
    assert destination.read_bytes() == b"winner"


def test_gate_receipt_rollback_removes_owned_file(tmp_path: Path) -> None:
    gate = _gate_receipt(gate_status="blocked")
    result = record_promotion_gate_receipt(
        gate,
        evidence_root=tmp_path / "evidence",
        relative_path="figure.promotion-gate.json",
    )
    destination = tmp_path / "evidence" / result.relative_path
    assert destination.exists()

    discard_promotion_gate_receipt(result, evidence_root=tmp_path / "evidence")

    assert not destination.exists()


def test_gate_receipt_rollback_preserves_replaced_inode(tmp_path: Path) -> None:
    receipt = _gate_receipt(gate_status="blocked")
    result = record_promotion_gate_receipt(
        receipt,
        evidence_root=tmp_path / "evidence",
        relative_path="figure.promotion-gate.json",
    )
    destination = tmp_path / "evidence" / result.relative_path
    replacement = destination.with_name("replacement.json")
    replacement.write_bytes(b"competitor")
    os.replace(replacement, destination)

    with pytest.raises(PromotionGateRecordingError, match="ownership"):
        discard_promotion_gate_receipt(result, evidence_root=tmp_path / "evidence")
    assert destination.read_bytes() == b"competitor"
