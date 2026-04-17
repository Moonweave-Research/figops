import os
import tempfile

import pytest

from plotting.figure_assembler import (
    assemble_figure,
    compute_slots,
    parse_layout,
)


def _create_mock_svg(path: str, width_mm: int = 50, label: str = "Mock"):
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg width="{width_mm}mm" height="{width_mm}mm" '
        f'viewBox="0 0 {width_mm} {width_mm}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width_mm}" height="{width_mm}" fill="red"/>'
        f'<text x="10" y="25" font-size="8pt">{label}</text>'
        f'</svg>'
    )
    with open(path, 'w') as f:
        f.write(svg)


class TestParseLayout:
    def test_simple_row(self):
        assert parse_layout("abc") == [['a', 'b', 'c']]

    def test_multirow(self):
        grid = parse_layout("aab\nccc")
        assert grid == [['a', 'a', 'b'], ['c', 'c', 'c']]

    def test_empty_cell(self):
        grid = parse_layout("a.b\nccc")
        assert grid[0][1] == '.'


class TestComputeSlots:
    def test_equal_three_columns(self):
        grid = parse_layout("abc")
        slots = compute_slots(grid, target_width_mm=183, gap_mm=3)
        # 3 cols: (183 - 3*2) / 3 = 59mm each
        assert abs(slots['a']['width_mm'] - 59.0) < 0.01
        assert abs(slots['b']['width_mm'] - 59.0) < 0.01
        assert abs(slots['c']['width_mm'] - 59.0) < 0.01

    def test_col_span(self):
        grid = parse_layout("aab\nccc")
        slots = compute_slots(grid, target_width_mm=183, gap_mm=3)
        # a spans 2 cols: 59*2 + 3 = 121mm
        assert abs(slots['a']['width_mm'] - 121.0) < 0.01
        # c spans 3 cols: full width = 183mm
        assert abs(slots['c']['width_mm'] - 183.0) < 0.01


class TestAssembleFigure:
    def test_basic_assembly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_mock_svg(os.path.join(tmpdir, "p1.svg"), 100, "P1")
            _create_mock_svg(os.path.join(tmpdir, "p2.svg"), 50, "P2")

            cfg = {
                "target_width_mm": 100,
                "gap_mm": 2,
                "layout": "ab",
                "panels": {
                    "a": {"source": "p1.svg"},
                    "b": {"source": "p2.svg"},
                },
            }

            out_path = assemble_figure("Test_Fig", cfg, tmpdir)

            assert os.path.exists(out_path)
            with open(out_path) as f:
                content = f.read()
            # Panel tags injected
            assert '(a)' in content
            assert '(b)' in content
            # Font attributes present on tags
            assert 'font-weight="bold"' in content

    def test_font_compensation_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_mock_svg(os.path.join(tmpdir, "wide.svg"), 200, "Wide")

            cfg = {
                "target_width_mm": 100,
                "gap_mm": 0,
                "layout": "a",
                "panels": {
                    "a": {"source": "wide.svg", "font_strategy": "compensate"},
                },
            }

            out_path = assemble_figure("Comp_Fig", cfg, tmpdir)

            with open(out_path) as f:
                content = f.read()
            # 200mm -> 100mm = scale 0.5, so 8pt should become 16pt
            assert '16.00pt' in content

    def test_missing_source_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "target_width_mm": 100,
                "gap_mm": 0,
                "layout": "a",
                "panels": {"a": {"source": "nonexistent.svg"}},
            }
            with pytest.raises(FileNotFoundError):
                assemble_figure("Err_Fig", cfg, tmpdir)

    def test_raster_png_embed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal valid PNG (1x1 red pixel)
            import struct
            import zlib

            def _mini_png(path):
                sig = b'\x89PNG\r\n\x1a\n'
                ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
                ihdr = _chunk(b'IHDR', ihdr_data)
                raw = b'\x00\xff\x00\x00'  # filter byte + RGB
                idat = _chunk(b'IDAT', zlib.compress(raw))
                iend = _chunk(b'IEND', b'')
                with open(path, 'wb') as f:
                    f.write(sig + ihdr + idat + iend)

            def _chunk(ctype, data):
                c = ctype + data
                crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
                return struct.pack('>I', len(data)) + c + crc

            png_path = os.path.join(tmpdir, "sem.png")
            _mini_png(png_path)

            cfg = {
                "target_width_mm": 100,
                "gap_mm": 0,
                "layout": "a",
                "panels": {"a": {"source": "sem.png", "font_strategy": "as_is"}},
            }

            out_path = assemble_figure("PNG_Fig", cfg, tmpdir)
            assert os.path.exists(out_path)
            with open(out_path) as f:
                content = f.read()
            assert 'data:image/png;base64,' in content
            assert '(a)' in content
