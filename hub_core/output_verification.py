from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_RASTER_FORMATS = {
    ".bmp": "BMP",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}
_PDF_TAIL_BYTES = 65_536
_PDF_XREF_PROBE_BYTES = 65_536


def _verify_raster(path: Path, expected_format: str) -> tuple[bool, str]:
    try:
        with Image.open(path) as image:
            actual_format = image.format
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as exc:
        return False, f"invalid {expected_format} image: {path} ({exc})"
    if actual_format != expected_format:
        return False, f"mismatched image format: expected {expected_format}, found {actual_format}"
    return True, f"valid {expected_format} image"


def _verify_svg(path: Path) -> tuple[bool, str]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError, UnicodeError) as exc:
        return False, f"invalid SVG XML: {path} ({exc})"
    local_name = root.tag.rsplit("}", 1)[-1].lower()
    if local_name != "svg":
        return False, f"invalid SVG root element: {root.tag}"
    return True, "valid SVG document"


def _verify_pdf(path: Path, file_size: int) -> tuple[bool, str]:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
            handle.seek(max(0, file_size - _PDF_TAIL_BYTES))
            tail = handle.read(_PDF_TAIL_BYTES)
    except OSError as exc:
        return False, f"cannot read PDF: {path} ({exc})"
    if not re.fullmatch(rb"%PDF-\d\.\d(?:\r?\n|\r).*", header, flags=re.DOTALL):
        return False, f"invalid PDF header: {path}"
    if not re.search(rb"%%EOF\s*\Z", tail):
        return False, f"missing PDF EOF marker: {path}"
    start_matches = list(re.finditer(rb"startxref\s+(\d+)\s+%%EOF", tail))
    if not start_matches:
        return False, f"missing PDF startxref: {path}"
    xref_offset = int(start_matches[-1].group(1))
    if xref_offset < 0 or xref_offset >= file_size:
        return False, f"invalid PDF xref offset: {path}"
    try:
        with path.open("rb") as handle:
            handle.seek(xref_offset)
            xref_head = handle.read(_PDF_XREF_PROBE_BYTES).lstrip()
    except OSError as exc:
        return False, f"cannot read PDF xref: {path} ({exc})"
    if _is_xref_table(xref_head) or _is_xref_stream(xref_head):
        return True, "valid PDF structure"
    return False, f"invalid PDF xref structure: {path}"


def _is_xref_table(xref_data: bytes) -> bool:
    return bool(
        re.match(
            rb"xref\s+\d+\s+\d+\s+(?:\d{10}\s+\d{5}\s+[fn]\s*(?:\r?\n|\r))+trailer\s*<<",
            xref_data,
        )
    )


def _is_xref_stream(xref_data: bytes) -> bool:
    match = re.match(
        rb"\d+\s+\d+\s+obj\s*<<(.*?)>>\s*stream(?:\r?\n|\r)",
        xref_data,
        flags=re.DOTALL,
    )
    if match is None:
        return False
    dictionary = match.group(1)
    return bool(
        re.search(rb"/Type\s*/XRef\b", dictionary)
        and re.search(rb"/Size\s+\d+\b", dictionary)
        and re.search(rb"/W\s*\[\s*\d+\s+\d+\s+\d+\s*\]", dictionary)
    )


def _verify_eps(path: Path, file_size: int) -> tuple[bool, str]:
    try:
        with path.open("rb") as handle:
            header = handle.read(64)
            handle.seek(max(0, file_size - 4096))
            tail = handle.read(4096)
    except OSError as exc:
        return False, f"cannot read EPS: {path} ({exc})"
    if not header.startswith(b"%!PS-Adobe-") or b"EPSF-" not in header:
        return False, f"invalid EPS header: {path}"
    if not re.search(rb"%%EOF\s*\Z", tail):
        return False, f"missing EPS EOF marker: {path}"
    return True, "valid EPS document"


def verify_output_file(output_path: str | os.PathLike[str]) -> tuple[bool, str]:
    path = Path(output_path)
    if not path.exists():
        return False, f"missing file: {path}"
    if not path.is_file():
        return False, f"output is not a regular file: {path}"
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        return False, f"cannot stat output: {path} ({exc})"
    if file_size <= 0:
        return False, f"empty file (0 byte): {path}"

    suffix = path.suffix.lower()
    if suffix in _RASTER_FORMATS:
        valid, detail = _verify_raster(path, _RASTER_FORMATS[suffix])
    elif suffix == ".svg":
        valid, detail = _verify_svg(path)
    elif suffix == ".pdf":
        valid, detail = _verify_pdf(path, file_size)
    elif suffix == ".eps":
        valid, detail = _verify_eps(path, file_size)
    else:
        return False, f"unsupported output format: {suffix or '<none>'}"
    if not valid:
        return False, detail
    return True, f"{path} ({file_size} bytes; {detail})"
