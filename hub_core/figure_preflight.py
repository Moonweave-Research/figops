"""
Publication figure preflight validator.
Checks generated figure files against journal submission requirements.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .journal_specs import ERROR, PREFLIGHT_POLICY_TOKENS, JournalToken, get_preflight_spec

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

    spec = get_preflight_spec(target_journal)

    suffix = figure_path.suffix.lower()
    is_raster = suffix in _RASTER_EXTENSIONS
    is_vector = suffix in _VECTOR_EXTENSIONS

    checks: list[dict[str, str | bool | None]] = []
    warnings: list[str] = []

    def add_check(name: str, passed: bool, detail: str, token: JournalToken | None = None) -> None:
        check: dict[str, str | bool | None] = {"name": name, "passed": passed, "detail": detail}
        if token is not None:
            check.update(
                {
                    "provenance": token.provenance,
                    "enforcement": token.enforcement,
                    "source_url": token.source_url,
                    "source_note": token.source_note,
                }
            )
        checks.append(check)

    # 1. Format check
    format_token = spec.formats
    accepted = set(format_token.value)
    fmt_ext = suffix.lstrip(".")
    if fmt_ext in ("tif",):
        fmt_ext = "tiff"
    if fmt_ext == "jpeg":
        fmt_ext = "jpg"
    if fmt_ext == "jpg" and fmt_ext not in accepted:
        add_check(
            "format",
            False,
            f"JPEG format not accepted for scientific figures ({target_journal})",
            format_token,
        )
    elif fmt_ext not in accepted:
        add_check(
            "format",
            False,
            f"'.{fmt_ext}' not in accepted formats: {sorted(accepted)}",
            format_token,
        )
    else:
        add_check("format", True, f"'.{fmt_ext}' accepted by {target_journal}", format_token)

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
            add_check("dpi", True, "DPI metadata not found (skipped)", spec.min_dpi)
            warnings.append("DPI metadata not found")
        else:
            min_observed = min(dpi_tuple)
            min_required = int(spec.min_dpi.value)
            # Allow 1 DPI tolerance for floating-point rounding (e.g., 599.999 ≈ 600)
            dpi_pass = min_observed >= min_required - 1
            add_check(
                "dpi",
                dpi_pass,
                f"{dpi_tuple[0]:.0f}x{dpi_tuple[1]:.0f} DPI (min: {min_required})",
                spec.min_dpi,
            )
    else:
        add_check("dpi", True, "Vector format — DPI check skipped", spec.min_dpi)

    # 3. Dimensions check (raster only)
    if is_raster and img is not None:
        width_px, height_px = img.size
        if dpi_tuple is not None:
            width_mm = width_px / dpi_tuple[0] * 25.4
            height_mm = height_px / dpi_tuple[1] * 25.4
            max_w = float(spec.max_width_mm.value)
            dims_pass = width_mm <= max_w
            if not dims_pass:
                warnings.append(f"Width {width_mm:.1f}mm exceeds journal max {max_w}mm")
            add_check(
                "dimensions",
                dims_pass,
                f"{width_mm:.1f}mm x {height_mm:.1f}mm (max width: {max_w:g}mm)",
                spec.max_width_mm,
            )
        else:
            add_check(
                "dimensions",
                True,
                f"{width_px}x{height_px} px (DPI unknown, mm conversion skipped)",
                spec.max_width_mm,
            )
    else:
        add_check("dimensions", True, "Vector format — dimension check skipped", spec.max_width_mm)

    # 4. Font settings check
    # For existing artifacts, parent-process matplotlib rcParams are not evidence:
    # MCP project renders execute plotting scripts in a subprocess. Inspect the PDF
    # artifact itself when possible; skip the check for non-PDF outputs.
    if suffix == ".pdf":
        try:
            pdf_bytes = figure_path.read_bytes()
        except OSError as exc:
            add_check(
                "font_settings",
                False,
                f"PDF font check failed: {exc}",
                PREFLIGHT_POLICY_TOKENS["font_settings"],
            )
        else:
            if b"/Subtype /Type3" in pdf_bytes or b"/Subtype/Type3" in pdf_bytes:
                warnings.append("PDF contains Type3 fonts; use pdf.fonttype=42 for embedded TrueType fonts")
                add_check(
                    "font_settings",
                    False,
                    "Type3 fonts detected",
                    PREFLIGHT_POLICY_TOKENS["font_settings"],
                )
            else:
                add_check(
                    "font_settings",
                    True,
                    "No Type3 PDF fonts detected",
                    PREFLIGHT_POLICY_TOKENS["font_settings"],
                )
    elif is_vector:
        add_check(
            "font_settings",
            True,
            "Font embedding check skipped for non-PDF vector format",
            PREFLIGHT_POLICY_TOKENS["font_settings"],
        )
    else:
        add_check(
            "font_settings",
            True,
            "Font embedding check skipped for raster format",
            PREFLIGHT_POLICY_TOKENS["font_settings"],
        )

    # 5. File size check
    file_bytes = figure_path.stat().st_size
    if is_raster and img is not None:
        width_px, height_px = img.size
        channels = len(img.getbands())
        expected_bytes = width_px * height_px * channels / 3 * 1.5
        # Dense/photographic rasters (e.g. SEM insets) can legitimately exceed
        # 0.5x raw-uncompressed size, so this is a warning, not a hard gate.
        if file_bytes > expected_bytes:
            file_mb = file_bytes / (1024 * 1024)
            expected_mb = expected_bytes / (1024 * 1024)
            warnings.append(f"File size {file_mb:.1f}MB exceeds expected {expected_mb:.1f}MB")
        add_check(
            "file_size",
            True,
            f"{file_bytes / (1024 * 1024):.1f}MB (raster)",
            PREFLIGHT_POLICY_TOKENS["raster_file_size"],
        )
    elif is_vector:
        size_pass = file_bytes <= _VECTOR_MAX_BYTES
        if not size_pass:
            warnings.append(f"File size {file_bytes / (1024 * 1024):.1f}MB exceeds 50MB limit")
        add_check(
            "file_size",
            size_pass,
            f"{file_bytes / (1024 * 1024):.1f}MB (vector, limit: 50MB)",
            PREFLIGHT_POLICY_TOKENS["vector_file_size"],
        )
    else:
        add_check(
            "file_size",
            True,
            f"{file_bytes / (1024 * 1024):.1f}MB",
            PREFLIGHT_POLICY_TOKENS["raster_file_size"],
        )

    # 6. Color mode check (raster only)
    if is_raster and img is not None:
        mode = img.mode
        color_pass = mode != "CMYK"
        if not color_pass:
            warnings.append("CMYK detected; most submission systems expect RGB")
        add_check(
            "color_mode",
            color_pass,
            f"Mode: {mode}",
            PREFLIGHT_POLICY_TOKENS["color_mode"],
        )
    else:
        add_check(
            "color_mode",
            True,
            "Vector format — color mode check skipped",
            PREFLIGHT_POLICY_TOKENS["color_mode"],
        )

    passed = all(c["passed"] or c.get("enforcement") != ERROR for c in checks)

    return {
        "passed": passed,
        "checks": checks,
        "warnings": warnings,
    }
