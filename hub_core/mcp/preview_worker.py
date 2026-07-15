"""Private bounded preview conversion worker.

The parent process supplies only files inside a private temporary directory.
This module is not an MCP surface and must not receive runtime artifact paths.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

MAX_PREVIEW_PIXELS: Final = 8_000_000
MAX_PREVIEW_EDGE: Final = 2_048
MAX_PREVIEW_BYTES: Final = 2 * 1024 * 1024


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")


def _poppler_executable(name: str) -> str | None:
    discovered = shutil.which(name)
    if not discovered:
        return None
    candidate = Path(discovered)
    if candidate.suffix.lower() == ".exe" and candidate.is_file():
        return str(candidate)
    if candidate.suffix.lower() in {".cmd", ".bat"}:
        dependencies = candidate.parent.parent.parent
        native = dependencies / "native" / "poppler" / "Library" / "bin" / f"{name}.exe"
        if native.is_file():
            return str(native)
    return None


def _encode_bounded_image(source: Path, output: Path) -> dict[str, Any]:
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_PREVIEW_PIXELS
    try:
        with Image.open(source) as opened:
            width, height = int(opened.width), int(opened.height)
            if width <= 0 or height <= 0 or width * height > MAX_PREVIEW_PIXELS:
                return {"status": "unavailable", "code": "PREVIEW_PIXEL_LIMIT"}
            image = ImageOps.exif_transpose(opened)
            image.load()
            image.thumbnail((MAX_PREVIEW_EDGE, MAX_PREVIEW_EDGE), Image.Resampling.LANCZOS)
            width, height = int(image.width), int(image.height)
            if width <= 0 or height <= 0 or width * height > MAX_PREVIEW_PIXELS:
                return {"status": "unavailable", "code": "PREVIEW_PIXEL_LIMIT"}
            image.save(output, format="PNG", optimize=True)
            media_type = "image/png"
            if output.stat().st_size > MAX_PREVIEW_BYTES:
                if image.mode not in {"RGB", "L"}:
                    background = Image.new("RGB", image.size, "white")
                    alpha = image.getchannel("A") if "A" in image.getbands() else None
                    background.paste(image.convert("RGB"), mask=alpha)
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                for quality in (90, 82, 74, 66, 58):
                    image.save(output, format="JPEG", quality=quality, optimize=True, progressive=False)
                    if output.stat().st_size <= MAX_PREVIEW_BYTES:
                        media_type = "image/jpeg"
                        break
                else:
                    return {"status": "unavailable", "code": "PREVIEW_BYTE_LIMIT"}
    except (OSError, ValueError, Image.DecompressionBombError):
        return {"status": "unavailable", "code": "RASTER_DECODE_FAILED"}
    return {
        "status": "available",
        "media_type": media_type,
        "width": width,
        "height": height,
        "byte_size": output.stat().st_size,
    }


def _render_pdf(source: Path, output: Path) -> dict[str, Any]:
    executable = _poppler_executable("pdftoppm")
    pdfinfo = _poppler_executable("pdfinfo")
    if executable is None or pdfinfo is None:
        return {"status": "unavailable", "code": "PDF_RENDERER_UNAVAILABLE"}
    info_path = output.with_name("pdfinfo.txt")
    try:
        with info_path.open("xb") as info_stream:
            info = subprocess.run(
                [pdfinfo, str(source)],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=info_stream,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            )
        if info.returncode != 0 or info_path.stat().st_size > 64 * 1024:
            return {"status": "unavailable", "code": "PDF_RENDER_FAILED"}
        match = re.search(rb"(?m)^Pages:\s*(\d+)\s*$", info_path.read_bytes())
        if match is None:
            return {"status": "unavailable", "code": "PDF_RENDER_FAILED"}
        if int(match.group(1)) != 1:
            return {"status": "unavailable", "code": "PDF_PAGE_LIMIT"}
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "code": "PDF_RENDER_TIMEOUT"}
    except OSError:
        return {"status": "unavailable", "code": "PDF_RENDER_FAILED"}
    prefix = output.with_suffix("")
    command = [
        executable,
        "-f",
        "1",
        "-l",
        "1",
        "-singlefile",
        "-png",
        "-scale-to",
        str(MAX_PREVIEW_EDGE),
        str(source),
        str(prefix),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4.0,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "code": "PDF_RENDER_TIMEOUT"}
    except OSError:
        return {"status": "unavailable", "code": "PDF_RENDER_FAILED"}
    generated = prefix.with_suffix(".png")
    if completed.returncode != 0 or not generated.is_file():
        return {"status": "unavailable", "code": "PDF_RENDER_FAILED"}
    if generated != output:
        generated.replace(output)
    return _encode_bounded_image(output, output)


def _inspect_svg(source: Path) -> dict[str, Any]:
    try:
        raw = source.read_bytes()
    except OSError:
        return {"status": "unavailable", "code": "SVG_PARSE_FAILED"}
    lowered = raw.lower()
    unsafe_tokens = (
        b"<!doctype",
        b"<!entity",
        b"<script",
        b"foreignobject",
        b"javascript:",
        b"data:",
        b"url(",
        b"@import",
    )
    if any(token in lowered for token in unsafe_tokens):
        return {"status": "unavailable", "code": "SVG_ACTIVE_CONTENT"}
    try:
        root = ElementTree.fromstring(raw)
    except Exception:
        return {"status": "unavailable", "code": "SVG_PARSE_FAILED"}
    for element in root.iter():
        local_name = str(element.tag).rsplit("}", 1)[-1].lower()
        if local_name in {"script", "foreignobject"}:
            return {"status": "unavailable", "code": "SVG_ACTIVE_CONTENT"}
        for name, value in element.attrib.items():
            attr = str(name).rsplit("}", 1)[-1].lower()
            text = str(value).strip().lower()
            if attr.startswith("on") or (attr == "href" and text and not text.startswith("#")):
                return {"status": "unavailable", "code": "SVG_ACTIVE_CONTENT"}
    # No renderer has passed the required Windows smoke test. Safe SVG remains
    # explicit unavailable; source SVG bytes are never returned as a preview.
    return {"status": "unavailable", "code": "SVG_RENDERER_UNAVAILABLE"}


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--media-type", required=True)
    args = parser.parse_args()
    source = Path(args.source)
    output = Path(args.output)
    result_path = Path(args.result)
    if args.media_type in {"image/png", "image/jpeg", "image/webp"}:
        result = _encode_bounded_image(source, output)
    elif args.media_type == "application/pdf":
        result = _render_pdf(source, output)
    elif args.media_type == "image/svg+xml":
        result = _inspect_svg(source)
    else:
        result = {"status": "unavailable", "code": "MEDIA_TYPE_UNSUPPORTED"}
    _write_result(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
