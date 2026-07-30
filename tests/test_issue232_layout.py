"""Regression coverage for issue #232's fixed-width Nature exports."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest
from PIL import Image

import themes.journal_theme as journal_theme
from themes.journal_theme import apply_journal_theme, mm_to_inch, save_journal_fig


@pytest.fixture(autouse=True)
def _restore_journal_state():
    saved_rc = plt.rcParams.copy()
    saved_state = {
        name: getattr(journal_theme, name)
        for name in (
            "_ACTIVE_TARGET_FORMAT",
            "_ACTIVE_FONT_TOKENS",
            "_ACTIVE_COMPLIANCE_TOKENS",
            "_ACTIVE_COMPLIANCE_MODE",
        )
    }
    yield
    plt.close("all")
    plt.rcParams.update(saved_rc)
    for name, value in saved_state.items():
        setattr(journal_theme, name, value)


def _render_labeled_figure(path, label: str, **save_kwargs) -> tuple[int, int]:
    """Render an unlocked 180 mm figure with an artist outside the axes box."""
    fig, ax = plt.subplots(figsize=(mm_to_inch(180.0), mm_to_inch(100.0)))
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.14, top=0.92)
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.text(1.2, 0.5, label, transform=ax.transAxes, clip_on=False)
    save_journal_fig(fig, path, dpi=600, tiff_companion=False, **save_kwargs)
    with Image.open(path) as image:
        return image.size


def _render_direct_labeled_figure(path, label: str, **save_kwargs) -> tuple[int, int]:
    """Render through Matplotlib directly, exercising the theme rcParams."""
    fig, ax = plt.subplots(figsize=(mm_to_inch(180.0), mm_to_inch(100.0)))
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.14, top=0.92)
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.text(1.2, 0.5, label, transform=ax.transAxes, clip_on=False)
    fig.savefig(path, dpi=600, **save_kwargs)
    with Image.open(path) as image:
        return image.size


def test_nature_auto_policy_keeps_png_canvas_width_when_label_changes(tmp_path):
    apply_journal_theme("nature")

    short_size = _render_labeled_figure(tmp_path / "short.png", "A")
    long_size = _render_labeled_figure(
        tmp_path / "long.png",
        "A very long label that would expand a tight bounding box substantially",
    )

    expected_width_px = int(mm_to_inch(180.0) * 600)
    assert short_size[0] == long_size[0] == expected_width_px
    assert short_size[1] == long_size[1]
    assert short_size[0] * 25.4 / 600 == pytest.approx(180.0, abs=0.1)


def test_nature_rc_default_keeps_direct_png_canvas_width_when_label_changes(tmp_path):
    apply_journal_theme("nature")

    short_size = _render_direct_labeled_figure(tmp_path / "direct-short.png", "A")
    long_size = _render_direct_labeled_figure(
        tmp_path / "direct-long.png",
        "A very long label that would expand a tight bounding box substantially",
    )

    expected_width_px = int(mm_to_inch(180.0) * 600)
    assert short_size[0] == long_size[0] == expected_width_px


def test_tight_bbox_remains_an_explicit_opt_in_for_nature(tmp_path):
    apply_journal_theme("nature")

    short_size = _render_labeled_figure(tmp_path / "tight-short.png", "A", bbox_policy="tight")
    long_size = _render_labeled_figure(
        tmp_path / "tight-long.png",
        "A very long label that would expand a tight bounding box substantially",
        bbox_inches="tight",
    )

    assert long_size[0] > short_size[0]


def test_direct_tight_bbox_remains_an_explicit_opt_in_for_nature(tmp_path):
    apply_journal_theme("nature")

    short_size = _render_direct_labeled_figure(tmp_path / "direct-tight-short.png", "A", bbox_inches="tight")
    long_size = _render_direct_labeled_figure(
        tmp_path / "direct-tight-long.png",
        "A very long label that would expand a tight bounding box substantially",
        bbox_inches="tight",
    )

    assert long_size[0] > short_size[0]


def test_fixed_bbox_policy_can_opt_in_for_non_nature_tracks(tmp_path):
    apply_journal_theme("science")

    size = _render_labeled_figure(
        tmp_path / "science-fixed.png",
        "A very long label that would otherwise expand a tight bounding box",
        bbox_policy="fixed",
    )

    assert size[0] == int(mm_to_inch(180.0) * 600)


def test_non_nature_theme_keeps_legacy_tight_rc_default(tmp_path):
    apply_journal_theme("science")
    assert plt.rcParams["savefig.bbox"] == "tight"

    short_size = _render_direct_labeled_figure(tmp_path / "science-tight-short.png", "A")
    long_size = _render_direct_labeled_figure(
        tmp_path / "science-tight-long.png",
        "A very long label that expands the tight bounding box",
    )

    assert long_size[0] > short_size[0]


def test_bbox_policy_rejects_unknown_values(tmp_path):
    apply_journal_theme("nature")

    with pytest.raises(ValueError, match="bbox_policy"):
        _render_labeled_figure(tmp_path / "invalid.png", "A", bbox_policy="crop")
