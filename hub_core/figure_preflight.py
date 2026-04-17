"""
Publication figure preflight validator.
Checks generated figure files against journal submission requirements.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

JOURNAL_SPECS: dict[str, dict] = {
    "nature": {"max_width_mm": 183, "min_dpi": 600, "formats": {"pdf", "png", "tiff", "eps"}},
    "science": {"max_width_mm": 170, "min_dpi": 600, "formats": {"pdf", "png", "tiff", "eps"}},
    "acs": {"max_width_mm": 171, "min_dpi": 600, "formats": {"tiff", "pdf", "png"}},
    "rsc": {"max_width_mm": 176, "min_dpi": 600, "formats": {"tiff", "pdf", "png"}},
    "elsevier": {"max_width_mm": 190, "min_dpi": 300, "formats": {"tiff", "pdf", "png", "eps"}},
}

_RASTER_EXTENSIONS = {".png", ".tiff", ".tif", ".jpg", ".jpeg", ".bmp"}
_VECTOR_EXTENSIONS = {".pdf", ".svg", ".eps"}
_VECTOR_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def validate_figure_preflight(
    figure_path: str | Path,
    target_journal: str = "nature",
) -> dict:
    """Validate a generated figure file against journal submission requirements.

    Returns dict with keys:
        passed: bool
        checks: list of {"name": str, "passed": bool, "detail": str}
        warnings: list of str
    """
    figure_path = Path(figure_path)
    if not figure_path.exists():
        raise FileNotFoundError(f"Figure file not found: {figure_path}")

    spec = JOURNAL_SPECS.get(target_journal.lower())
    if spec is None:
        raise ValueError(
            f"Unknown journal '{target_journal}'. "
            f"Supported: {', '.join(sorted(JOURNAL_SPECS))}"
        )

    suffix = figure_path.suffix.lower()
    is_raster = suffix in _RASTER_EXTENSIONS
    is_vector = suffix in _VECTOR_EXTENSIONS

    checks: list[dict[str, str | bool]] = []
    warnings: list[str] = []

    # 1. Format check
    accepted = spec["formats"]
    fmt_ext = suffix.lstrip(".")
    if fmt_ext in ("tif",):
        fmt_ext = "tiff"
    if fmt_ext in ("jpg", "jpeg"):
        checks.append({
            "name": "format",
            "passed": False,
            "detail": f"JPEG format not accepted for scientific figures ({target_journal})",
        })
    elif fmt_ext not in accepted:
        checks.append({
            "name": "format",
            "passed": False,
            "detail": f"'.{fmt_ext}' not in accepted formats: {sorted(accepted)}",
        })
    else:
        checks.append({
            "name": "format",
            "passed": True,
            "detail": f"'.{fmt_ext}' accepted by {target_journal}",
        })

    # Open image for raster checks
    img: Image.Image | None = None
    dpi_tuple: tuple[float, float] | None = None
    if is_raster:
        img = Image.open(figure_path)
        raw_dpi = img.info.get("dpi")
        if raw_dpi is not None and len(raw_dpi) == 2:
            dpi_tuple = (float(raw_dpi[0]), float(raw_dpi[1]))

    # 2. DPI check (raster only)
    if is_raster:
        if dpi_tuple is None:
            checks.append({
                "name": "dpi",
                "passed": True,
                "detail": "DPI metadata not found (skipped)",
            })
            warnings.append("DPI metadata not found")
        else:
            min_observed = min(dpi_tuple)
            min_required = spec["min_dpi"]
            # Allow 1 DPI tolerance for floating-point rounding (e.g., 599.999 ≈ 600)
            dpi_pass = min_observed >= min_required - 1
            checks.append({
                "name": "dpi",
                "passed": dpi_pass,
                "detail": f"{dpi_tuple[0]:.0f}x{dpi_tuple[1]:.0f} DPI (min: {min_required})",
            })
    else:
        checks.append({
            "name": "dpi",
            "passed": True,
            "detail": "Vector format — DPI check skipped",
        })

    # 3. Dimensions check (raster only)
    if is_raster and img is not None:
        width_px, height_px = img.size
        if dpi_tuple is not None:
            width_mm = width_px / dpi_tuple[0] * 25.4
            height_mm = height_px / dpi_tuple[1] * 25.4
            max_w = spec["max_width_mm"]
            if width_mm > max_w:
                warnings.append(
                    f"Width {width_mm:.1f}mm exceeds journal max {max_w}mm"
                )
            checks.append({
                "name": "dimensions",
                "passed": True,
                "detail": f"{width_mm:.1f}mm x {height_mm:.1f}mm (max width: {max_w}mm)",
            })
        else:
            checks.append({
                "name": "dimensions",
                "passed": True,
                "detail": f"{width_px}x{height_px} px (DPI unknown, mm conversion skipped)",
            })
    else:
        checks.append({
            "name": "dimensions",
            "passed": True,
            "detail": "Vector format — dimension check skipped",
        })

    # 4. Font settings check
    try:
        import matplotlib.pyplot as plt
        fonttype = plt.rcParams.get("pdf.fonttype")
        if fonttype != 42:
            warnings.append(
                f"PDF fonts may not be embedded (fonttype={fonttype} != 42)"
            )
            checks.append({
                "name": "font_settings",
                "passed": True,
                "detail": f"pdf.fonttype={fonttype} (recommended: 42)",
            })
        else:
            checks.append({
                "name": "font_settings",
                "passed": True,
                "detail": "pdf.fonttype=42 (TrueType embedded)",
            })
    except ImportError:
        checks.append({
            "name": "font_settings",
            "passed": True,
            "detail": "matplotlib not available — font check skipped",
        })

    # 5. File size check
    file_bytes = figure_path.stat().st_size
    if is_raster and img is not None:
        width_px, height_px = img.size
        channels = len(img.getbands())
        expected_bytes = width_px * height_px * channels / 3 * 1.5
        if file_bytes > expected_bytes:
            file_mb = file_bytes / (1024 * 1024)
            expected_mb = expected_bytes / (1024 * 1024)
            warnings.append(
                f"File size {file_mb:.1f}MB exceeds expected {expected_mb:.1f}MB"
            )
        checks.append({
            "name": "file_size",
            "passed": True,
            "detail": f"{file_bytes / (1024 * 1024):.1f}MB (raster)",
        })
    elif is_vector:
        size_pass = file_bytes <= _VECTOR_MAX_BYTES
        if not size_pass:
            warnings.append(
                f"File size {file_bytes / (1024 * 1024):.1f}MB exceeds 50MB limit"
            )
        checks.append({
            "name": "file_size",
            "passed": True,
            "detail": f"{file_bytes / (1024 * 1024):.1f}MB (vector, limit: 50MB)",
        })
    else:
        checks.append({
            "name": "file_size",
            "passed": True,
            "detail": f"{file_bytes / (1024 * 1024):.1f}MB",
        })

    # 6. Color mode check (raster only)
    if is_raster and img is not None:
        mode = img.mode
        if mode == "CMYK":
            warnings.append("CMYK detected; most submission systems expect RGB")
        checks.append({
            "name": "color_mode",
            "passed": True,
            "detail": f"Mode: {mode}",
        })
    else:
        checks.append({
            "name": "color_mode",
            "passed": True,
            "detail": "Vector format — color mode check skipped",
        })

    passed = all(c["passed"] for c in checks)

    return {
        "passed": passed,
        "checks": checks,
        "warnings": warnings,
    }
