from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from hub_core.figure_preflight import validate_figure_preflight  # noqa: E402
from hub_core.journal_specs import ERROR
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT  # noqa: E402


@pytest.fixture(autouse=True)
def _cleanup_plots():
    yield
    plt.close("all")


def _save_dummy_figure(path: Path, *, dpi: int = 600, fmt: str = "png") -> Path:
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot([1, 2, 3])
    fig.savefig(path, dpi=dpi, format=fmt)
    plt.close(fig)
    return path


def test_valid_600dpi_png_passes(tmp_path: Path):
    png = _save_dummy_figure(tmp_path / "fig.png", dpi=600)
    result = validate_figure_preflight(png, "nature")
    assert result["passed"] is True
    assert not any("fonttype" in warning for warning in result["warnings"])
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert dpi_check["passed"] is True
    assert "600" in dpi_check["detail"]
    assert dpi_check["provenance"]
    assert dpi_check["enforcement"] == ERROR
    assert "source_note" in dpi_check


def test_low_dpi_png_fails(tmp_path: Path):
    png = _save_dummy_figure(tmp_path / "fig_low.png", dpi=72)
    result = validate_figure_preflight(png, "nature")
    assert result["passed"] is False
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert dpi_check["passed"] is False
    assert "72" in dpi_check["detail"]


def test_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        validate_figure_preflight("/nonexistent.png")


def test_jpeg_format_fails_for_nature(tmp_path: Path):
    jpg = tmp_path / "fig.jpg"
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot([1, 2, 3])
    fig.savefig(jpg, dpi=600, format="jpg")
    plt.close(fig)

    result = validate_figure_preflight(jpg, "nature")
    assert result["passed"] is False
    fmt_check = next(c for c in result["checks"] if c["name"] == "format")
    assert fmt_check["passed"] is False


def test_pdf_skips_dpi_check(tmp_path: Path):
    pdf = tmp_path / "fig.pdf"
    with plt.rc_context({"pdf.fonttype": 42}):
        fig, ax = plt.subplots(figsize=(3.5, 2.8))
        ax.plot([1, 2, 3])
        fig.savefig(pdf, format="pdf")
        plt.close(fig)

    result = validate_figure_preflight(pdf, "nature")
    assert result["passed"] is True
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert dpi_check["passed"] is True
    assert "skip" in dpi_check["detail"].lower()


def test_pdf_font_check_warns_on_type3_fonts(tmp_path: Path):
    pdf = tmp_path / "fig_type3.pdf"
    with plt.rc_context({"pdf.fonttype": 3}):
        fig, ax = plt.subplots(figsize=(3.5, 2.8))
        ax.plot([1, 2, 3])
        fig.savefig(pdf, format="pdf")
        plt.close(fig)

    result = validate_figure_preflight(pdf, "nature")

    assert result["passed"] is False
    assert any("Type3" in warning for warning in result["warnings"])
    font_check = next(c for c in result["checks"] if c["name"] == "font_settings")
    assert font_check["passed"] is False
    assert "Type3" in font_check["detail"]


def test_pdf_font_check_accepts_truetype_fonts(tmp_path: Path):
    pdf = tmp_path / "fig_truetype.pdf"
    with plt.rc_context({"pdf.fonttype": 42}):
        fig, ax = plt.subplots(figsize=(3.5, 2.8))
        ax.plot([1, 2, 3])
        fig.savefig(pdf, format="pdf")
        plt.close(fig)

    result = validate_figure_preflight(pdf, "nature")

    assert result["passed"] is True
    assert not any("Type3" in warning for warning in result["warnings"])
    font_check = next(c for c in result["checks"] if c["name"] == "font_settings")
    assert "No Type3" in font_check["detail"]


def test_over_width_raster_fails(tmp_path: Path):
    png = tmp_path / "fig_wide.png"
    # nature max width is 183mm; at 600 DPI that is ~4322px. Exceed it.
    img = Image.new("RGB", (5000, 1000), color="white")
    img.save(png, format="png", dpi=(600, 600))

    result = validate_figure_preflight(png, "nature")
    assert result["passed"] is False
    dims_check = next(c for c in result["checks"] if c["name"] == "dimensions")
    assert dims_check["passed"] is False
    assert any("exceeds journal max" in warning for warning in result["warnings"])


def test_over_width_svg_with_physical_units_fails(tmp_path: Path):
    svg = tmp_path / "wide.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="80mm">'
        '<rect width="200mm" height="80mm" fill="white"/></svg>',
        encoding="utf-8",
    )

    result = validate_figure_preflight(svg, "nature")

    assert result["passed"] is False
    dims_check = next(c for c in result["checks"] if c["name"] == "dimensions")
    assert dims_check["passed"] is False
    assert "200.0mm" in dims_check["detail"]


def test_cmyk_raster_fails(tmp_path: Path):
    tiff = tmp_path / "fig_cmyk.tiff"
    img = Image.new("CMYK", (800, 600), color=(0, 0, 0, 0))
    img.save(tiff, format="tiff", dpi=(600, 600))

    result = validate_figure_preflight(tiff, "nature")
    assert result["passed"] is False
    color_check = next(c for c in result["checks"] if c["name"] == "color_mode")
    assert color_check["passed"] is False
    assert color_check["detail"] == "Mode: CMYK"


def test_oversized_raster_file_size_warns_not_fails(tmp_path: Path):
    png = tmp_path / "fig_tiny.png"
    # 2x2 RGB -> expected_bytes = 2*2*3/3*1.5 = 6 bytes; any real PNG far exceeds this.
    img = Image.new("RGB", (2, 2), color="white")
    img.save(png, format="png", dpi=(600, 600))
    assert png.stat().st_size > 6

    result = validate_figure_preflight(png, "nature")
    size_check = next(c for c in result["checks"] if c["name"] == "file_size")
    # Dense/photographic rasters can legitimately exceed the 0.5x raw bound,
    # so this is a warning, not a hard gate.
    assert size_check["passed"] is True
    assert size_check["enforcement"] == "advisory"
    assert size_check["provenance"] == "graphhub_assumption"
    assert any("exceeds expected" in warning for warning in result["warnings"])


def test_oversized_vector_file_size_fails(tmp_path: Path):
    pdf = tmp_path / "fig.pdf"
    with plt.rc_context({"pdf.fonttype": 42}):
        _save_dummy_figure(pdf, fmt="pdf")

    class _BigStat:
        st_size = 51 * 1024 * 1024

    def fake_stat(self, *args, **kwargs):
        return _BigStat()

    with patch.object(Path, "stat", fake_stat):
        result = validate_figure_preflight(pdf, "nature")

    size_check = next(c for c in result["checks"] if c["name"] == "file_size")
    assert size_check["passed"] is False
    assert size_check["enforcement"] == ERROR
    assert any("exceeds 50MB limit" in warning for warning in result["warnings"])


def test_internal_style_preflight_is_marked_internal(tmp_path: Path):
    png = _save_dummy_figure(tmp_path / "fig.png", dpi=600)

    result = validate_figure_preflight(png, INTERNAL_STYLE_TARGET_FORMAT)

    assert result["passed"] is True
    fmt_check = next(c for c in result["checks"] if c["name"] == "format")
    assert fmt_check["provenance"] == "internal_project_style"
    assert "not a separate journal standard" in fmt_check["source_note"]


def test_wiley_preflight_target_is_supported(tmp_path: Path):
    png = _save_dummy_figure(tmp_path / "fig.png", dpi=300)

    result = validate_figure_preflight(png, "wiley")

    assert result["passed"] is True
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert "min: 300" in dpi_check["detail"]


def test_jpeg_passes_only_when_target_registry_allows_it(tmp_path: Path):
    jpg = tmp_path / "fig.jpg"
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot([1, 2, 3])
    fig.savefig(jpg, dpi=300, format="jpg")
    plt.close(fig)

    wiley = validate_figure_preflight(jpg, "wiley")
    nature = validate_figure_preflight(jpg, "nature")

    assert next(c for c in wiley["checks"] if c["name"] == "format")["passed"] is True
    assert next(c for c in nature["checks"] if c["name"] == "format")["passed"] is False


def test_unknown_preflight_target_reports_supported_targets(tmp_path: Path):
    png = _save_dummy_figure(tmp_path / "fig.png", dpi=600)

    with pytest.raises(ValueError, match="Supported"):
        validate_figure_preflight(png, "default")
