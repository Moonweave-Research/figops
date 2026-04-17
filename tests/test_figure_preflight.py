from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from hub_core.figure_preflight import validate_figure_preflight  # noqa: E402


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
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert dpi_check["passed"] is True
    assert "600" in dpi_check["detail"]


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
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot([1, 2, 3])
    fig.savefig(pdf, format="pdf")
    plt.close(fig)

    result = validate_figure_preflight(pdf, "nature")
    assert result["passed"] is True
    dpi_check = next(c for c in result["checks"] if c["name"] == "dpi")
    assert dpi_check["passed"] is True
    assert "skip" in dpi_check["detail"].lower()
