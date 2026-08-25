from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from figops import save_journal_fig
from hub_core.mcp import GraphHubMCPServer, McpServerConfig
from hub_core.mcp.render_geometry import geometry_verification_state
from hub_core.mcp.tools.render_csv_args import (
    _validated_plot_argument_compatibility,
    resolve_facet_plot_type,
)
from themes.cjk_text import warn_for_mixed_cjk_mathtext
from themes.compliance import apply_runtime_font_resolution


def test_public_save_journal_fig_import_is_available():
    assert callable(save_journal_fig)


def test_additional_project_root_allows_external_project_but_not_runtime(tmp_path: Path):
    research_root = tmp_path / "research"
    external_root = tmp_path / "nas"
    runtime_root = tmp_path / "runtime"
    project = external_root / "project"
    for path in (research_root, external_root, runtime_root, project):
        path.mkdir(parents=True, exist_ok=True)
    server = GraphHubMCPServer(
        config=McpServerConfig(
            research_root=research_root,
            runtime_root=runtime_root,
            allowed_project_roots=(external_root,),
        )
    )

    assert server._resolve_execution_project_path(str(project)) == project.resolve()
    with pytest.raises(ValueError, match="allowed project root"):
        server._resolve_execution_project_path(str(runtime_root))


def test_research_and_runtime_data_uris_resolve_under_server_owned_roots(tmp_path: Path):
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    runtime_root.mkdir()
    research_file = research_root / "input.csv"
    runtime_file = runtime_root / "input.csv"
    research_file.write_text("x,y\n1,2\n", encoding="utf-8")
    runtime_file.write_text("x,y\n1,2\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    assert server._resolve_allowed_data_path("research://input.csv", field_name="data_path") == research_file.resolve()
    assert server._resolve_allowed_data_path("runtime://input.csv", field_name="data_path") == runtime_file.resolve()
    with pytest.raises(ValueError, match="relative path"):
        server._resolve_allowed_data_path("runtime:///input.csv", field_name="data_path")


def test_line_plot_with_facet_column_is_promoted_and_keeps_series_styles_legal():
    plot_type, warning = resolve_facet_plot_type("line", "condition")
    compatibility = _validated_plot_argument_compatibility(
        plot_type=plot_type,
        raw_annotate_values=False,
        raw_bar_error_column="",
        raw_yerr_column="",
        raw_yerr_minus_column="",
        raw_yerr_cap_width=None,
        series_column="material",
        label_column="",
        point_label_options={},
        guide_curves=[],
        fill_between=[],
    )

    assert plot_type == "facet"
    assert warning and "promoted" in warning
    assert compatibility["errors"] == []


def test_cjk_font_family_is_concrete_and_mixed_mathtext_warns(monkeypatch):
    monkeypatch.setattr(
        "themes.font_fallbacks._CJK_FONT_CANDIDATES",
        {"darwin": ("Malgun Gothic",), "win32": ("Malgun Gothic",), "default": ()},
    )
    monkeypatch.setattr(
        "themes.font_fallbacks._installed_font_family_names",
        lambda: {"malgun gothic": "Malgun Gothic"},
    )
    theme_rc = {"font.sans-serif": ["Arial"], "mathtext.fontset": "custom"}
    apply_runtime_font_resolution(theme_rc)
    assert theme_rc["font.family"] == ["Arial", "DejaVu Sans", "Malgun Gothic"]

    fig, axis = plt.subplots()
    axis.set_title("전기전도도 $\\sigma$")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert warn_for_mixed_cjk_mathtext(fig) == 1
    plt.close(fig)
    assert any("mixed with mathtext" in str(item.message) for item in captured)


def test_missing_style_geometry_has_a_distinct_unverified_state():
    state = geometry_verification_state(
        {"measurements": [{"metric_id": "geometry_diagnostics", "availability": "unavailable"}]},
        validation_target="nature",
    )

    assert state["status"] == "unverified"
    assert "3 required geometry checks" in state["summary"]


def test_malformed_style_geometry_is_not_treated_as_verified():
    state = geometry_verification_state(
        {
            "measurements": [
                {
                    "metric_id": "style_geometry_observations",
                    "availability": "available",
                    "value": {"figure_height_mm": 60, "font_sizes": "invalid", "line_widths": []},
                }
            ]
        },
        validation_target="nature",
    )

    assert state["status"] == "unverified"
    assert "malformed or incomplete" in state["summary"]
