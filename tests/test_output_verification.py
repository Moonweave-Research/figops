from unittest.mock import patch

import pytest
from PIL import Image

from hub_core.process_runner import run_plots
from hub_core.utils import verify_output_file


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    [(".png", "PNG"), (".jpg", "JPEG"), (".tiff", "TIFF"), (".bmp", "BMP")],
)
def test_valid_raster_formats_pass_structural_verification(tmp_path, suffix, image_format):
    output = tmp_path / f"valid{suffix}"
    Image.new("RGB", (4, 4), color="white").save(output, format=image_format)

    valid, message = verify_output_file(output)

    assert valid, message


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        (".png", b"\x89PNG\r\n\x1a\n"),
        (".jpg", b"\xff\xd8"),
        (".tiff", b"II*\x00"),
        (".bmp", b"BM"),
        (".pdf", b"%PDF-1.7\n"),
        (".svg", b"<svg"),
        (".eps", b"%!PS-Adobe-3.0 EPSF-3.0\n"),
    ],
)
def test_truncated_supported_formats_fail_closed(tmp_path, suffix, payload):
    output = tmp_path / f"truncated{suffix}"
    output.write_bytes(payload)

    valid, _message = verify_output_file(output)

    assert not valid


def test_mislabeled_raster_fails_closed(tmp_path):
    output = tmp_path / "mislabeled.png"
    Image.new("RGB", (4, 4), color="white").save(output, format="JPEG")

    valid, _message = verify_output_file(output)

    assert not valid


def test_forged_pdf_with_non_xref_object_at_startxref_fails_closed(tmp_path):
    output = tmp_path / "forged.pdf"
    output.write_bytes(
        b"%PDF-1.7\n"
        b"1 0 obj\n"
        b"not-a-valid-pdf\n"
        b"endobj\n"
        b"startxref\n"
        b"9\n"
        b"%%EOF\n"
    )

    valid, message = verify_output_file(output)

    assert not valid
    assert "xref" in message.lower()


def test_valid_svg_pdf_and_eps_pass(tmp_path):
    import matplotlib.pyplot as plt

    svg = tmp_path / "valid.svg"
    svg.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
        encoding="utf-8",
    )
    pdf = tmp_path / "valid.pdf"
    fig, ax = plt.subplots()
    try:
        ax.plot([0, 1], [0, 1])
        fig.savefig(pdf)
    finally:
        plt.close(fig)
    eps = tmp_path / "valid.eps"
    eps.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 1 1\nshowpage\n%%EOF\n")

    results = [verify_output_file(path)[0] for path in (svg, pdf, eps)]

    assert results == [True, True, True]


def test_unsupported_extension_fails_closed(tmp_path):
    output = tmp_path / "figure.webp"
    Image.new("RGB", (4, 4), color="white").save(output, format="WEBP")

    valid, message = verify_output_file(output)

    assert not valid
    assert "unsupported" in message.lower()


class _Prefetcher:
    def ensure_local(self, _paths: list[str]) -> None:
        return None


class _Athena:
    def load_solve_context_env(self) -> dict[str, str]:
        return {}


def test_process_runner_rejects_corrupt_output_without_recording_build_state(tmp_path):
    script = tmp_path / "plot.py"
    script.write_text("# test fixture\n", encoding="utf-8")
    output = tmp_path / "results" / "figures" / "figure.pdf"
    build_state_path = tmp_path / ".build_state.json"
    build_state: dict = {}
    config = {
        "project": {"name": "CorruptOutput"},
        "language_policy": {"analysis_lang": "r", "plot_lang": "python", "allow_nonstandard": False},
        "visual_style": {"target_format": "nature", "font_scale": 1.0, "profile": "baseline"},
        "figures": [{"id": "Fig1", "script": "plot.py", "output": "results/figures/figure.pdf"}],
        "diagrams": [],
    }

    def write_corrupt_output(*_args, **_kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"%PDF-1.7\n")
        return True

    with (
        patch("hub_core.process_runner.is_executable_available", return_value=True),
        patch("hub_core.process_runner.run_command", side_effect=write_corrupt_output),
    ):
        result = run_plots(
            str(tmp_path),
            config,
            build_state,
            str(build_state_path),
            "config-hash",
            force=True,
            prefetcher=_Prefetcher(),
            athena=_Athena(),
        )

    assert not result
    assert build_state == {}
    assert not build_state_path.exists()
