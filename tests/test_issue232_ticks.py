import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogFormatterSciNotation

from hub_core.geometry_diagnostics import diagnose_figure_geometry
from themes.journal_theme import (
    apply_journal_theme,
    apply_narrow_log_minor_tick_policy,
    save_journal_fig,
)


def _draw_narrow_log(target="nature"):
    apply_journal_theme(target)
    fig, ax = plt.subplots(figsize=(3, 2), dpi=100)
    ax.set_xscale("log")
    ax.set_xlim(28, 338)
    ax.plot([30, 300], [1, 2])
    fig.canvas.draw()
    return fig, ax


def test_journal_auto_suppresses_only_minor_labels_in_narrow_log_range():
    fig, ax = _draw_narrow_log()
    try:
        major_before = [label.get_text() for label in ax.get_xticklabels() if label.get_text()]
        minor_before = [label.get_text() for label in ax.get_xticklabels(minor=True) if label.get_text()]

        evidence = apply_narrow_log_minor_tick_policy(fig)
        fig.canvas.draw()

        assert major_before
        # Matplotlib 3.10 does not render default minor labels for this
        # one-decade range, while newer releases do.  The policy contract is
        # the journal evidence and post-policy suppression; pre-policy label
        # presence is renderer-version dependent.
        assert [label.get_text() for label in ax.get_xticklabels() if label.get_text()] == major_before
        if minor_before:
            assert [label.get_text() for label in ax.get_xticklabels(minor=True) if label.get_text()] == []
        assert evidence["axes"] == [
            {
                "axis_index": 0,
                "axis": "x",
                "decades": evidence["axes"][0]["decades"],
                "applied": True,
                "restored": False,
                "reason": "narrow_log_range",
            }
        ]
    finally:
        plt.close(fig)


def test_narrow_log_policy_is_target_scoped_and_preserves_custom_formatter():
    fig, ax = _draw_narrow_log("ppt")
    try:
        before = ax.xaxis.get_minor_formatter()
        before_thresholds = tuple(before.minor_thresholds)
        apply_narrow_log_minor_tick_policy(fig, mode=True)
        assert ax.xaxis.get_minor_formatter() is before
        assert tuple(before.minor_thresholds) == before_thresholds
    finally:
        plt.close(fig)

    fig, ax = _draw_narrow_log("nature")
    try:
        custom = FuncFormatter(lambda value, position: f"custom-{value:g}")
        ax.xaxis.set_minor_formatter(custom)
        evidence = apply_narrow_log_minor_tick_policy(fig)
        assert ax.xaxis.get_minor_formatter() is custom
        assert evidence["axes"][0]["reason"] == "custom_minor_formatter"
    finally:
        plt.close(fig)


def test_narrow_log_policy_explicit_opt_out_restores_default_formatter(tmp_path):
    fig, ax = _draw_narrow_log()
    try:
        apply_narrow_log_minor_tick_policy(fig)
        assert tuple(ax.xaxis.get_minor_formatter().minor_thresholds) == (0.0, 0.0)
        save_journal_fig(fig, tmp_path / "opt_out.png", narrow_log_minor_labels=False, dpi=100)
        assert tuple(ax.xaxis.get_minor_formatter().minor_thresholds) == (1.0, 0.4)
    finally:
        plt.close(fig)


def test_narrow_log_policy_does_not_rewrite_post_policy_formatter_customization():
    fig, ax = _draw_narrow_log()
    try:
        apply_narrow_log_minor_tick_policy(fig)
        formatter = ax.xaxis.get_minor_formatter()
        formatter.minor_thresholds = (7.0, 7.0)
        evidence = apply_narrow_log_minor_tick_policy(fig)
        assert tuple(formatter.minor_thresholds) == (7.0, 7.0)
        assert evidence["axes"][0]["reason"] == "user_modified_formatter"
    finally:
        plt.close(fig)


def test_tick_overlap_evidence_includes_displayed_minor_labels_and_offset_text():
    fig, (log_ax, linear_ax) = plt.subplots(1, 2, figsize=(5, 2), dpi=100)
    try:
        log_ax.set_xscale("log")
        log_ax.set_xlim(28, 338)
        # Make the source labels deterministic across Matplotlib releases:
        # 3.10's default minor formatter leaves this narrow range blank,
        # whereas later releases display labels with the same defaults.
        log_ax.xaxis.set_minor_formatter(LogFormatterSciNotation(minor_thresholds=(2.0, 0.4)))
        log_ax.plot([30, 300], [1, 2])
        linear_ax.plot([1_000_000, 2_000_000], [1, 2])
        linear_ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0), useOffset=True)
        fig.canvas.draw()

        result = diagnose_figure_geometry(fig, [log_ax, linear_ax], layout_locked=False)
        checks = [check for check in result["checks"] if check["name"] == "tick_label_overlaps"]
        log_data = checks[0]["data"]
        offset_data = checks[1]["data"]

        assert log_data["x_minor_labels"]
        assert log_data["x_minor_overlap_pairs"]
        # Major indices remain the historical space; minor pairs are additive.
        assert log_data["x_overlap_pairs"] == []
        assert set(offset_data["x_offset_text"]) == {"text", "visible", "paintable", "displayed"}
        assert offset_data["x_offset_text"]["displayed"]
    finally:
        plt.close(fig)
