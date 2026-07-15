from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import matplotlib
import pytest
from cycler import cycler

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from hub_core.calculation_evidence import (  # noqa: E402
    verify_calculation_evidence,
    verify_calculation_evidence_bundle,
)
from hub_core.geometry_diagnostics import diagnose_figure_geometry  # noqa: E402
from hub_core.mcp import GraphHubMCPServer  # noqa: E402
from hub_core.mcp.render_geometry_schemas import GEOMETRY_DIAGNOSTICS_SCHEMA  # noqa: E402
from hub_core.mcp.schemas import list_plot_type_descriptions, list_tool_definitions  # noqa: E402
from plotting.bridge_renderer import BridgeFigureSpec, render_bridge_figure  # noqa: E402
from plotting.renderers.labels import display_label  # noqa: E402
from plotting.utils import label_transformation_evidence  # noqa: E402
from themes.declutter import _declutter_text_artists  # noqa: E402
from themes.journal_theme import apply_journal_theme, save_journal_fig  # noqa: E402


def _calculation_artifact(path: Path) -> tuple[Path, str, dict]:
    payload = {
        "schema_version": "figops_calculation_evidence/1",
        "evidence_id": "analysis:t-test:group-a-v-b",
        "producer": "analysis.py@sha256:fixture",
        "assertion": {"metric": "p_value", "operator": "lt", "threshold": 0.05, "display_label": "p=0.012"},
        "marker_binding": {"x1": 0, "x2": 1},
        "test_metadata": {"test_name": "welch_t_test", "model": "two-sided"},
        "result": {"status": "passed", "p_value": 0.012},
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), payload


def _marker(sha256: str, payload: dict) -> dict:
    return {
        "x1": 0,
        "x2": 1,
        "y": 2,
        "label": "p=0.012",
        "calculation_evidence_id": payload["evidence_id"],
        "analysis_artifact_sha256": sha256,
        "test_metadata": payload["test_metadata"],
    }


def test_labels_preserve_raw_and_record_explicit_collision_and_legacy_opt_in() -> None:
    assert display_label("ABC_DEF") == "ABC_DEF"
    assert display_label("ABC_DEF", label_map={"ABC_DEF": "Sample A"}) == "Sample A"
    assert display_label("ABC_DEF", label_transform="legacy_compress") == "ABC, DEF"

    evidence = label_transformation_evidence(
        ["ABC_DEF", "XYZ"],
        label_map={"ABC_DEF": "shared", "XYZ": "shared"},
    )
    assert evidence["collisions"] == [{"display": "shared", "originals": ["ABC_DEF", "XYZ"]}]
    assert len(evidence["mutation_ledger"]) == 2


def test_profile_palette_is_not_overwritten_and_explicit_palette_has_precedence() -> None:
    custom = cycler(color=["#123456", "#abcdef"])
    saved = plt.rcParams.copy()
    try:
        with patch("themes.journal_theme.get_profile_rc_overrides", return_value=({"axes.prop_cycle": custom}, "x")):
            apply_journal_theme("nature", profile_name="x")
            assert plt.rcParams["axes.prop_cycle"] == custom
            apply_journal_theme("nature", profile_name="x", palette=["#fedcba"])
            assert list(plt.rcParams["axes.prop_cycle"])[0]["color"] == "#fedcba"

        apply_journal_theme("nature", profile_name="baseline", palette=["#fedcba"])
        assert list(plt.rcParams["axes.prop_cycle"])[0]["color"] == "#fedcba"
    finally:
        plt.rcParams.update(saved)


def test_validate_mode_does_not_mutate_and_explicit_clamp_records_ledger(tmp_path: Path) -> None:
    apply_journal_theme("science", compliance_mode="validate")
    fig, ax = plt.subplots()
    text = ax.text(0.5, 0.5, "tiny", fontsize=2)
    line = ax.plot([0, 1], [0, 1], linewidth=0.1)[0]
    try:
        validate_ledger: list[dict] = []
        with patch.dict(os.environ, {"GRAPH_HUB_AUTO_DECLUTTER": "1"}):
            save_journal_fig(fig, tmp_path / "validate.png", mutation_ledger_out=validate_ledger, dpi=72)
        assert text.get_fontsize() == 2
        assert line.get_linewidth() == 0.1
        assert text.get_position() == (0.5, 0.5)
        assert validate_ledger == []

        clamp_ledger: list[dict] = []
        save_journal_fig(
            fig,
            tmp_path / "clamp.png",
            compliance_mode="clamp",
            mutation_ledger_out=clamp_ledger,
            dpi=72,
        )
        assert text.get_fontsize() >= 5
        assert line.get_linewidth() >= 0.5
        assert clamp_ledger
        assert all({"before", "after", "policy_id", "reason"} <= set(item) for item in clamp_ledger)
        assert {item["policy_id"] for item in clamp_ledger} == {"journal-science/baseline"}
    finally:
        plt.close(fig)


def test_bridge_render_persists_explicit_label_mapping_and_collision_evidence(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("condition,value\nABC_DEF,1\nXYZ,2\n", encoding="utf-8")
    sidecar = tmp_path / "authored.json"
    spec = BridgeFigureSpec(
        csv_path=str(data_path),
        output_path=str(tmp_path / "figure.png"),
        plot_type="bar",
        x_column="condition",
        y_column="value",
        title="Mapped labels",
        label_map={"ABC_DEF": "shared", "XYZ": "shared"},
    )
    with patch.dict(os.environ, {"AUTHORED_OUTPUT_EVIDENCE_OUT": str(sidecar)}):
        render_bridge_figure(spec)
    evidence = json.loads(sidecar.read_text(encoding="utf-8"))
    assert evidence["collisions"] == [{"display": "shared", "originals": ["ABC_DEF", "XYZ"]}]
    mappings = {item["original"]: item["display"] for item in evidence["mappings"]}
    assert mappings["ABC_DEF"] == "shared"
    assert mappings["XYZ"] == "shared"
    assert len(evidence["mutation_ledger"]) == 2


def test_bridge_default_renders_raw_tick_and_legend_text(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "condition,series,value\nABC_DEF,SERIES_ONE,1\nXYZ,SERIES_TWO,2\n",
        encoding="utf-8",
    )
    captured: dict[str, list[str]] = {}

    def capture_save(fig, filename, **kwargs):
        fig.canvas.draw()
        axis = fig.axes[0]
        captured["ticks"] = [text.get_text() for text in axis.get_xticklabels()]
        legend = axis.get_legend()
        captured["legend"] = [text.get_text() for text in legend.get_texts()] if legend else []
        return save_journal_fig(fig, filename, **kwargs)

    spec = BridgeFigureSpec(
        csv_path=str(data_path),
        output_path=str(tmp_path / "raw.png"),
        plot_type="bar",
        x_column="condition",
        y_column="value",
        series_column="series",
        title="Raw labels",
    )
    with patch("plotting.bridge_renderer.save_journal_fig", side_effect=capture_save):
        render_bridge_figure(spec)
    assert "ABC_DEF" in captured["ticks"]
    assert "SERIES_ONE" in captured["legend"]


def test_explicit_declutter_returns_before_after_and_convergence_evidence() -> None:
    fig, ax = plt.subplots()
    ax.text(0.5, 0.5, "A")
    ax.text(0.5, 0.5, "B")
    try:
        result = _declutter_text_artists(fig, max_iter=2)
        assert {"moved_text_artists", "converged", "before_after", "mutation_ledger"} <= set(result)
        assert result["moved_text_artists"] == len(result["before_after"])
    finally:
        plt.close(fig)


def test_raw_geometry_contract_contains_no_policy_fields() -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()
    try:
        result = diagnose_figure_geometry(fig, [ax], layout_locked=False, contract_version="raw")
    finally:
        plt.close(fig)
    assert result["schema_version"] == "geometry_diagnostics/2"
    forbidden = {"passed", "severity", "hard", "advisory", "outcome", "blocked", "threshold"}

    def walk(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value)
            policy_tokens = {
                "threshold",
                "minimum",
                "maximum",
                "limit",
                "severity",
                "verdict",
                "pass",
                "passed",
                "fail",
                "failed",
                "offender",
                "offenders",
            }
            assert not any(
                set(str(key).lower().replace("-", "_").split("_")) & policy_tokens
                for key in value
            )
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(result)
    assert all(
        {"metric_id", "availability", "unit", "scope"} <= set(item)
        and ((item["availability"] == "available" and "value" in item) or "reason" in item)
        for item in result["measurements"]
    )


def test_basic_worked_examples_do_not_invent_statistical_claims() -> None:
    for description in list_plot_type_descriptions():
        arguments = description["worked_example"]["arguments"]
        invented = {"fit_line", "ci_band", "fit_options", "significance_markers", "bar_error_column", "aggregate"}
        assert not (invented & arguments.keys())


def test_claim_schema_matches_closed_dispatch_and_bounded_bundle() -> None:
    render = next(
        tool for tool in list_tool_definitions() if tool["name"] == "figops.render_csv_graph"
    )
    properties = render["inputSchema"]["properties"]
    marker = properties["significance_markers"]["items"]
    assert "label" in marker["required"]
    assert "text" not in marker["properties"]
    assert marker["properties"]["test_metadata"]["additionalProperties"] is False
    assert properties["calculation_evidence_paths"]["maxItems"] == 32


def test_significance_requires_and_accepts_verified_independent_artifact(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    evidence_path, evidence_sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    arguments = {
        "data_path": "data.csv",
        "x_column": "x",
        "y_column": "y",
        "plot_type": "scatter",
        "significance_markers": [_marker(evidence_sha, payload)],
        "calculation_evidence_path": evidence_path.name,
        "dry_run": True,
        "job_id": "linked-claim",
    }

    accepted = server.call_tool("figops.render_csv_graph", arguments)["structuredContent"]
    assert accepted["status"] == "ok"

    real_arguments = {**arguments, "dry_run": False, "job_id": "linked-claim-real"}
    rendered = server.call_tool("figops.render_csv_graph", real_arguments)["structuredContent"]
    assert rendered["status"] in {"ok", "warning"}
    assert rendered["calculation_evidence"][0]["artifact_ref"] == evidence_path.name

    multipanel = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [
                {
                    "data_path": "data.csv",
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "significance_markers": [_marker(evidence_sha, payload)],
                    "calculation_evidence_path": evidence_path.name,
                }
            ],
            "rows": 1,
            "cols": 1,
            "job_id": "linked-claim-multipanel-real",
        },
    )["structuredContent"]
    assert multipanel["status"] in {"ok", "warning"}
    assert multipanel["calculation_evidence"][0]["artifact_ref"] == evidence_path.name

    arguments["significance_markers"][0]["analysis_artifact_sha256"] = "0" * 64
    rejected = server.call_tool("figops.render_csv_graph", arguments)["structuredContent"]
    assert rejected["status"] == "error"
    assert "does not match" in json.dumps(rejected)


def test_direct_significance_without_contained_artifact_is_rejected(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contained calculation evidence"):
        render_bridge_figure(
            BridgeFigureSpec(
                csv_path=str(data_path),
                output_path=str(tmp_path / "figure.png"),
                plot_type="scatter",
                x_column="x",
                y_column="y",
                title="unsupported",
                significance_markers=(
                    {
                        "x1": 0,
                        "x2": 1,
                        "y": 2,
                        "calculation_evidence_id": "fake",
                        "analysis_artifact_sha256": "0" * 64,
                        "test_metadata": {"test_name": "fake", "model": "fake"},
                    },
                ),
            )
        )


@pytest.mark.parametrize("declared", ["../outside.json", "C:/outside.json"])
def test_calculation_evidence_rejects_traversal_and_absolute_paths(tmp_path: Path, declared: str) -> None:
    with pytest.raises(ValueError):
        verify_calculation_evidence(tmp_path, declared)


def test_calculation_evidence_rejects_oversize_and_malformed_result(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="exceeds"):
        verify_calculation_evidence(tmp_path, oversized.name)

    malformed = tmp_path / "malformed.json"
    _path, _sha, payload = _calculation_artifact(malformed)
    payload["result"]["p_value"] = float("nan")
    malformed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        verify_calculation_evidence(tmp_path, malformed.name)


def test_calculation_evidence_size_limit_cannot_be_widened(tmp_path: Path) -> None:
    evidence_path, _sha, _payload = _calculation_artifact(tmp_path / "calculation.json")
    with pytest.raises(TypeError):
        verify_calculation_evidence(tmp_path, evidence_path.name, max_bytes=2 * 1024 * 1024)  # type: ignore[call-arg]


def test_calculation_evidence_rejects_false_assertion_and_forged_marker_fields(tmp_path: Path) -> None:
    evidence_path, evidence_sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    payload["result"]["p_value"] = 0.9
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not satisfy"):
        verify_calculation_evidence(tmp_path, evidence_path.name)

    _path, evidence_sha, payload = _calculation_artifact(evidence_path)
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    base = {
        "data_path": "data.csv",
        "x_column": "x",
        "y_column": "y",
        "plot_type": "scatter",
        "calculation_evidence_path": evidence_path.name,
        "dry_run": True,
    }
    for forged in ({"label": "***"}, {"x2": 2}):
        marker = _marker(evidence_sha, payload)
        marker.update(forged)
        result = server.call_tool(
            "figops.render_csv_graph", {**base, "significance_markers": [marker]}
        )["structuredContent"]
        assert result["status"] == "error"


def test_calculation_evidence_rejects_unknown_path_and_large_string_injection(tmp_path: Path) -> None:
    evidence_path, _sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    payload["artifact_path"] = "C:/secret/private.txt"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported fields") as error:
        verify_calculation_evidence(tmp_path, evidence_path.name)
    assert "C:/secret" not in str(error.value)

    payload.pop("artifact_path")
    payload["producer"] = "x" * 257
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 256"):
        verify_calculation_evidence(tmp_path, evidence_path.name)


def test_geometry_output_schema_is_frozen_raw_v2() -> None:
    assert GEOMETRY_DIAGNOSTICS_SCHEMA["properties"]["schema_version"] == {
        "const": "geometry_diagnostics/2"
    }
    assert set(GEOMETRY_DIAGNOSTICS_SCHEMA["required"]) == {
        "schema_version",
        "measurements",
        "warnings",
    }
    assert "checks" not in GEOMETRY_DIAGNOSTICS_SCHEMA["properties"]
    assert "passed" not in GEOMETRY_DIAGNOSTICS_SCHEMA["properties"]


def test_calculation_evidence_rejects_symlink_component(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-calculation.json"
    _calculation_artifact(outside)
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    try:
        with pytest.raises(ValueError):
            verify_calculation_evidence(tmp_path, link.name)
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction witness")
def test_calculation_evidence_rejects_in_root_windows_junction(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    _calculation_artifact(real / "evidence.json")
    junction = tmp_path / "junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(real)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable")
    try:
        with pytest.raises(ValueError, match="symlink, junction, or reparse"):
            verify_calculation_evidence(tmp_path, "junction/evidence.json")
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("p_value", True),
        ("p_value", "0.012"),
        ("threshold", False),
        ("threshold", "0.05"),
        ("x1", True),
        ("x2", "1"),
    ],
)
def test_calculation_evidence_rejects_bool_and_numeric_strings(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path, _sha, payload = _calculation_artifact(tmp_path / f"{field}.json")
    if field == "p_value":
        payload["result"][field] = value
    elif field == "threshold":
        payload["assertion"][field] = value
    else:
        payload["marker_binding"][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON number"):
        verify_calculation_evidence(tmp_path, path.name)


def test_marker_rejects_bool_numeric_string_and_unknown_fields_without_echo(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    evidence_path, evidence_sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    base = {
        "data_path": data.name,
        "x_column": "x",
        "y_column": "y",
        "plot_type": "scatter",
        "calculation_evidence_path": evidence_path.name,
        "dry_run": True,
    }
    for field, value in (("x1", True), ("x2", "1"), ("h", False)):
        marker = _marker(evidence_sha, payload)
        marker[field] = value
        result = server.call_tool(
            "figops.render_csv_graph", {**base, "significance_markers": [marker]}
        )["structuredContent"]
        assert result["status"] == "error"
        assert "JSON number" in json.dumps(result)

    marker = _marker(evidence_sha, payload)
    marker["artifact_path"] = "C:/secret/do-not-echo.txt"
    result = server.call_tool(
        "figops.render_csv_graph",
        {**base, "job_id": "closed-marker", "dry_run": False, "significance_markers": [marker]},
    )["structuredContent"]
    assert result["status"] == "error"
    assert "do-not-echo" not in json.dumps(result)
    assert not (tmp_path / "runtime" / "mcp_jobs" / "closed-marker").exists()


def test_calculation_json_rejects_duplicate_keys_at_nested_depth(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version":"figops_calculation_evidence/1",'
        '"evidence_id":"a","producer":"p",'
        '"test_metadata":{"test_name":"t","test_name":"forged","model":"m"},'
        '"result":{"status":"passed","p_value":0.01},'
        '"assertion":{"metric":"p_value","operator":"lt","threshold":0.05,"display_label":"p<0.05"},'
        '"marker_binding":{"x1":0,"x2":1}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate object keys"):
        verify_calculation_evidence(tmp_path, path.name)


def test_authored_pvalue_typography_and_explicit_stars_remain_valid(tmp_path: Path) -> None:
    variants = [
        ("p = 0.012", "lt", 0.05, 0.012, None),
        ("p ≤ .05", "le", 0.05, 0.012, None),
        ("***", "lt", 0.001, 0.0005, {"*": 0.05, "**": 0.01, "***": 0.001}),
    ]
    for index, (label, operator, threshold, p_value, stars) in enumerate(variants):
        path, _sha, payload = _calculation_artifact(tmp_path / f"variant-{index}.json")
        payload["result"]["p_value"] = p_value
        payload["assertion"].update(
            {"operator": operator, "threshold": threshold, "display_label": label}
        )
        if stars is not None:
            payload["assertion"]["star_thresholds"] = stars
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        assert verify_calculation_evidence(tmp_path, path.name)["assertion"]["display_label"] == label

    custom, _sha, payload = _calculation_artifact(tmp_path / "custom.json")
    payload["assertion"].update(
        {"display_label": "adjusted q = 0.012 (BH)", "display_kind": "custom"}
    )
    custom.write_text(json.dumps(payload), encoding="utf-8")
    normalized = verify_calculation_evidence(tmp_path, custom.name)
    assert normalized["assertion"]["display_label"] == "adjusted q = 0.012 (BH)"
    assert normalized["assertion"]["display_kind"] == "custom"

    payload["assertion"].update({"display_label": "p<0.01", "display_kind": "threshold"})
    custom.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="contradicts"):
        verify_calculation_evidence(tmp_path, custom.name)


def test_bundle_prefetches_once_opens_each_once_and_canonicalizes_refs(tmp_path: Path) -> None:
    first, _sha, payload = _calculation_artifact(tmp_path / "evidence-a.json")
    second = tmp_path / "nested" / "evidence-b.json"
    second.parent.mkdir()
    payload["evidence_id"] = "analysis:t-test:second"
    payload["marker_binding"] = {"x1": 2, "x2": 3}
    second.write_text(json.dumps(payload), encoding="utf-8")

    calls: list[list[str]] = []

    class CountingPrefetcher:
        def ensure_local(self, paths: list[str]) -> None:
            calls.append(paths)

    with patch(
        "hub_core.calculation_evidence.select_adapters",
        return_value=SimpleNamespace(prefetcher=CountingPrefetcher()),
    ), patch("hub_core.calculation_evidence.open_verified_project_input", wraps=__import__(
        "hub_core.calculation_evidence", fromlist=["open_verified_project_input"]
    ).open_verified_project_input) as opened:
        records = verify_calculation_evidence_bundle(
            tmp_path,
            ["./evidence-a.json", "nested//evidence-b.json", "evidence-a.json"],
        )

    assert len(calls) == 1
    assert len(calls[0]) == 2
    assert opened.call_count == 2
    assert [record["artifact_ref"] for record in records] == [
        "evidence-a.json",
        "nested/evidence-b.json",
    ]


def test_post_prefetch_component_change_fails_before_any_evidence_bytes_are_read(tmp_path: Path) -> None:
    evidence, _sha, _payload = _calculation_artifact(tmp_path / "evidence.json")
    calls = 0

    class CountingPrefetcher:
        def ensure_local(self, paths: list[str]) -> None:
            nonlocal calls
            calls += 1
            assert paths == [str(evidence)]

    with (
        patch(
            "hub_core.calculation_evidence.select_adapters",
            return_value=SimpleNamespace(prefetcher=CountingPrefetcher()),
        ),
        patch(
            "hub_core.calculation_evidence.project_path_has_symlink_component",
            side_effect=[False, True],
        ),
        patch("hub_core.calculation_evidence.open_verified_project_input") as opened,
    ):
        with pytest.raises(ValueError, match="changed to a symlink"):
            verify_calculation_evidence(tmp_path, evidence.name)
    assert calls == 1
    opened.assert_not_called()


def test_bundle_rejects_duplicate_ids_and_multiple_claims_render_in_one_call(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n2,3\n", encoding="utf-8")
    first, first_sha, first_payload = _calculation_artifact(tmp_path / "first.json")
    second = tmp_path / "second.json"
    second_payload = json.loads(json.dumps(first_payload))
    second_payload["evidence_id"] = "analysis:t-test:second"
    second_payload["assertion"]["display_label"] = "p < .05"
    second_payload["marker_binding"] = {"x1": 1, "x2": 2}
    second.write_text(json.dumps(second_payload), encoding="utf-8")
    second_sha = hashlib.sha256(second.read_bytes()).hexdigest()

    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    result = server.call_tool(
        "figops.render_csv_graph",
        {
            "data_path": data.name,
            "x_column": "x",
            "y_column": "y",
            "plot_type": "scatter",
            "calculation_evidence_paths": [first.name, second.name],
            "significance_markers": [
                _marker(first_sha, first_payload),
                {
                    **_marker(second_sha, second_payload),
                    "x1": 1,
                    "x2": 2,
                    "y": 2.5,
                    "label": "p < .05",
                },
            ],
            "job_id": "two-claims",
        },
    )["structuredContent"]
    assert result["status"] in {"ok", "warning"}
    assert len(result["calculation_evidence"]) == 2
    assert len(result["statistical_claims"]) == 2

    second_payload["evidence_id"] = first_payload["evidence_id"]
    second.write_text(json.dumps(second_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate evidence_id"):
        verify_calculation_evidence_bundle(tmp_path, [first.name, second.name])


def test_multipanel_rejects_unscoped_duplicate_claim_and_quick_ci(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    evidence, sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    marker = _marker(sha, payload)
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    duplicated = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [
                {
                    "data_path": data.name,
                    "x_column": "x",
                    "y_column": "y",
                    "significance_markers": [marker],
                    "calculation_evidence_path": evidence.name,
                },
                {
                    "data_path": data.name,
                    "x_column": "x",
                    "y_column": "y",
                    "significance_markers": [marker],
                    "calculation_evidence_path": evidence.name,
                },
            ],
            "rows": 1,
            "cols": 2,
            "dry_run": True,
        },
    )["structuredContent"]
    assert duplicated["status"] == "error"
    assert "claimed more than once" in json.dumps(duplicated)

    ci = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [
                {"data_path": data.name, "x_column": "x", "y_column": "y", "ci_band": True}
            ],
            "dry_run": True,
        },
    )["structuredContent"]
    assert ci["status"] == "error"
    assert "ci_band is unavailable" in json.dumps(ci)


def test_multipanel_distinct_claims_and_compat_alias_use_same_closed_lane(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    first, first_sha, first_payload = _calculation_artifact(tmp_path / "first.json")
    second = tmp_path / "second.json"
    second_payload = json.loads(json.dumps(first_payload))
    second_payload["evidence_id"] = "analysis:t-test:second-panel"
    second_payload["assertion"]["display_label"] = "p = 0.012"
    second.write_text(json.dumps(second_payload), encoding="utf-8")
    second_sha = hashlib.sha256(second.read_bytes()).hexdigest()
    second_marker = _marker(second_sha, second_payload)
    second_marker["label"] = "p = 0.012"

    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    result = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [
                {
                    "data_path": data.name,
                    "x_column": "x",
                    "y_column": "y",
                    "significance_markers": [_marker(first_sha, first_payload)],
                    "calculation_evidence_path": first.name,
                },
                {
                    "data_path": data.name,
                    "x_column": "x",
                    "y_column": "y",
                    "significance_markers": [second_marker],
                    "calculation_evidence_paths": [second.name],
                },
            ],
            "rows": 1,
            "cols": 2,
            "job_id": "distinct-panel-claims",
        },
    )["structuredContent"]
    assert result["status"] in {"ok", "warning"}
    assert {item["evidence_id"] for item in result["calculation_evidence"]} == {
        first_payload["evidence_id"],
        second_payload["evidence_id"],
    }
    assert len(result["provenance"]["calculation_evidence_refs"]) == 2

    unsupported = server.call_tool(
        "graphhub.render_csv_graph",
        {
            "data_path": data.name,
            "x_column": "x",
            "y_column": "y",
            "significance_markers": [_marker(first_sha, first_payload)],
            "dry_run": True,
        },
    )["structuredContent"]
    assert unsupported["status"] == "error"
    assert "verified calculation evidence" in json.dumps(unsupported)

    ci = server.call_tool(
        "graphhub.render_csv_graph",
        {"data_path": data.name, "x_column": "x", "y_column": "y", "ci_band": True},
    )["structuredContent"]
    assert ci["status"] == "error"
    assert "ci_band is unavailable" in json.dumps(ci)


def test_generic_annotation_claim_candidates_do_not_bypass_evidence(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    base = {"data_path": data.name, "x_column": "x", "y_column": "y", "dry_run": True}

    for text in ("p<0.05", "***"):
        result = server.call_tool(
            "figops.render_csv_graph",
            {**base, "annotations": [{"x": 0.5, "y": 1.5, "text": text}]},
        )["structuredContent"]
        assert result["status"] == "error"
        assert "claim candidate" in json.dumps(result)

    ordinary = server.call_tool(
        "figops.render_csv_graph",
        {**base, "annotations": [{"x": 0.5, "y": 1.5, "text": "phase transition"}]},
    )["structuredContent"]
    assert ordinary["status"] == "ok"
    assert ordinary.get("claim_candidates", []) == []

    compat = server.call_tool(
        "graphhub.render_csv_graph",
        {**base, "annotations": [{"x": 0.5, "y": 1.5, "text": "p=.01"}]},
    )["structuredContent"]
    assert compat["status"] == "error"


def test_literal_annotation_preserves_text_and_records_bounded_manual_review(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    text = "  p<0.05  "
    result = server.call_tool(
        "figops.render_csv_graph",
        {
            "data_path": data.name,
            "x_column": "x",
            "y_column": "y",
            "annotations": [{"x": 0.5, "y": 1.5, "text": text, "annotation_kind": "literal"}],
            "job_id": "literal-claim",
        },
    )["structuredContent"]
    assert result["status"] == "warning"
    assert result["manual_review_needed"] is True
    assert result["claim_candidates"][0]["text"] == text
    assert result["claim_candidates"][0]["text_truncated"] is False
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["claim_candidates"] == result["claim_candidates"]

    huge = "p<0.05" + ("x" * 1000)
    bounded = server.call_tool(
        "figops.render_csv_graph",
        {
            "data_path": data.name,
            "x_column": "x",
            "y_column": "y",
            "annotations": [{"x": 0, "y": 1, "text": huge, "annotation_kind": "literal"}],
            "dry_run": True,
        },
    )["structuredContent"]
    assert len(bounded["claim_candidates"][0]["text"]) == 512
    assert bounded["claim_candidates"][0]["text_truncated"] is True


def test_generic_annotation_can_link_exact_producer_claim_and_direct_path_fails_closed(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    evidence, sha, payload = _calculation_artifact(tmp_path / "calculation.json")
    annotation = {
        "x": 0.5,
        "y": 1.5,
        "text": payload["assertion"]["display_label"],
        "annotation_kind": "statistical_claim",
        "calculation_evidence_id": payload["evidence_id"],
        "analysis_artifact_sha256": sha,
        "test_metadata": payload["test_metadata"],
    }
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    result = server.call_tool(
        "figops.render_csv_graph",
        {
            "data_path": data.name,
            "x_column": "x",
            "y_column": "y",
            "annotations": [annotation],
            "calculation_evidence_path": evidence.name,
            "job_id": "annotation-claim",
        },
    )["structuredContent"]
    assert result["status"] in {"ok", "warning"}
    assert result["statistical_claims"][0]["source"] == "annotation"

    direct = BridgeFigureSpec(
        csv_path=str(data),
        output_path=str(tmp_path / "direct.png"),
        plot_type="scatter",
        x_column="x",
        y_column="y",
        title="",
        annotations=({"x": 0.5, "y": 1.5, "text": "p<0.05"},),
    )
    with pytest.raises(ValueError, match="trusted, preverified"):
        render_bridge_figure(direct)

    literal = BridgeFigureSpec(
        csv_path=str(data),
        output_path=str(tmp_path / "literal-direct.png"),
        plot_type="scatter",
        x_column="x",
        y_column="y",
        title="",
        annotations=({"x": 0.5, "y": 1.5, "text": "  p<0.05  ", "annotation_kind": "literal"},),
    )
    direct_evidence = tmp_path / "direct-authored-output.json"
    with patch.dict(os.environ, {"AUTHORED_OUTPUT_EVIDENCE_OUT": str(direct_evidence)}):
        render_bridge_figure(literal)
    assert Path(literal.output_path).is_file()
    ledger = json.loads(direct_evidence.read_text(encoding="utf-8"))["claim_candidates"]
    assert ledger[0]["text"] == "  p<0.05  "
    assert ledger[0]["manual_review_required"] is True


def test_inferential_fill_band_requires_future_interval_evidence(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y,lo,hi\n0,1,0,2\n1,2,1,3\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    base = {"data_path": data.name, "x_column": "x", "y_column": "y", "dry_run": True}
    rejected = server.call_tool(
        "figops.render_csv_graph",
        {
            **base,
            "fill_between": [{
                "x_column": "x", "y1_column": "lo", "y2_column": "hi",
                "label": "95% CI", "band_kind": "confidence_interval",
            }],
        },
    )["structuredContent"]
    assert rejected["status"] == "error"
    assert "interval evidence" in json.dumps(rejected)

    descriptive = server.call_tool(
        "figops.render_csv_graph",
        {**base, "fill_between": [{"x_column": "x", "y1_column": "lo", "y2_column": "hi", "label": "95% CI"}]},
    )["structuredContent"]
    assert descriptive["status"] == "ok"

    literal = server.call_tool(
        "figops.render_csv_graph",
        {**base, "fill_between": [{
            "x_column": "x", "y1_column": "lo", "y2_column": "hi",
            "label": "95% CI", "band_kind": "literal",
        }]},
    )["structuredContent"]
    assert literal["status"] == "warning"
    assert literal["claim_candidates"][0]["source"] == "fill_between"


def test_multipanel_annotation_claim_candidates_share_the_closed_lane(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    base_panel = {"data_path": data.name, "x_column": "x", "y_column": "y"}
    rejected = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [{**base_panel, "annotations": [{"x": 0, "y": 1, "text": "p<.05"}]}],
            "dry_run": True,
        },
    )["structuredContent"]
    assert rejected["status"] == "error"

    literal = server.call_tool(
        "figops.render_csv_multipanel",
        {
            "panels": [{
                **base_panel,
                "annotations": [{"x": 0, "y": 1, "text": "***", "annotation_kind": "literal"}],
            }],
            "dry_run": True,
        },
    )["structuredContent"]
    assert literal["status"] == "warning"
    assert literal["manual_review_needed"] is True
    assert literal["claim_candidates"][0]["panel_index"] == 0
