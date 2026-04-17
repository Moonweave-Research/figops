from __future__ import annotations

import base64
import mimetypes
import os
import re
import uuid

import svgutils.transform as sg
from lxml import etree

MM_TO_PX = 3.7795275591
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)\s*(px|pt|mm)?")
URL_REF_RE = re.compile(r"url\(#([^)]+)\)")
TAG_FONT_SIZE_PT = 8
RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}
RELATIVE_UNITS = {'%', 'em', 'ex', 'rem', 'ch', 'vw', 'vh'}
FONT_SHORTHAND_RE = re.compile(
    r"font\s*:\s*"
    r"(?:(?:italic|oblique|normal)\s+)?"      # font-style (optional)
    r"(?:(?:bold|[1-9]00|normal|lighter|bolder)\s+)?"  # font-weight (optional)
    r"([\d.]+(?:px|pt|mm|em)?)"                # font-size (capture group 1)
    r"(?:\s*/\s*[\d.]+(?:px|pt|mm|em)?)?"      # line-height (optional)
    r"\s+([^;]+)"                               # font-family — stop at semicolon
)
CSS_FILL_RE = re.compile(r'(?:^|;)\s*fill\s*:\s*([^;]+)')
CSS_STROKE_RE = re.compile(r'(?:^|;)\s*stroke\s*:\s*([^;]+)')
CSS_STROKE_WIDTH_RE = re.compile(r'(?:^|;)\s*stroke-width\s*:\s*([^;]+)')
CSS_OPACITY_RE = re.compile(r'(?:^|;)\s*(?<!fill-)(?<!stroke-)opacity\s*:\s*([^;]+)')


# ── Layout Parser ────────────────────────────────────────────────

def parse_layout(layout_str: str) -> list[list[str]]:
    rows = []
    for line in layout_str.strip().splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(list(stripped))
    return rows


def validate_layout_contiguous(grid: list[list[str]]) -> list[str]:
    """Check that each panel character forms a contiguous rectangle in the grid."""
    errors = []
    chars: dict[str, list[tuple[int, int]]] = {}
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch == '.':
                continue
            chars.setdefault(ch, []).append((r, c))

    for ch, cells in chars.items():
        rows_set = {r for r, _ in cells}
        cols_set = {c for _, c in cells}
        expected = len(rows_set) * len(cols_set)
        if len(cells) != expected:
            errors.append(
                f"Layout character '{ch}' does not form a contiguous rectangle "
                f"(found {len(cells)} cells, expected {expected} for "
                f"{len(rows_set)} rows x {len(cols_set)} cols)."
            )
    return errors


def compute_slots(
    grid: list[list[str]],
    target_width_mm: float,
    gap_mm: float,
    row_height_ratios: list[float] | None = None,
) -> dict[str, dict]:
    n_rows = len(grid)
    n_cols = len(grid[0])

    col_unit = (target_width_mm - gap_mm * (n_cols - 1)) / n_cols

    bounds: dict[str, dict] = {}
    for r, row in enumerate(grid):
        for c, char in enumerate(row):
            if char == '.':
                continue
            if char not in bounds:
                bounds[char] = {'min_r': r, 'max_r': r, 'min_c': c, 'max_c': c}
            else:
                bounds[char]['min_r'] = min(bounds[char]['min_r'], r)
                bounds[char]['max_r'] = max(bounds[char]['max_r'], r)
                bounds[char]['min_c'] = min(bounds[char]['min_c'], c)
                bounds[char]['max_c'] = max(bounds[char]['max_c'], c)

    if row_height_ratios and len(row_height_ratios) == n_rows:
        ratios = row_height_ratios
    else:
        ratios = [1.0] * n_rows
    ratio_sum = sum(ratios)

    row_heights_mm = [(r / ratio_sum) * col_unit * n_rows for r in ratios]

    row_y = [0.0]
    for i in range(n_rows - 1):
        row_y.append(row_y[-1] + row_heights_mm[i] + gap_mm)

    slots = {}
    for char, b in bounds.items():
        col_span = b['max_c'] - b['min_c'] + 1
        row_span = b['max_r'] - b['min_r'] + 1

        x_mm = b['min_c'] * (col_unit + gap_mm)
        y_mm = row_y[b['min_r']]
        width_mm = col_span * col_unit + (col_span - 1) * gap_mm
        height_mm = sum(row_heights_mm[b['min_r']:b['max_r']+1]) + (row_span - 1) * gap_mm

        slots[char] = {
            'x_mm': x_mm,
            'y_mm': y_mm,
            'width_mm': width_mm,
            'height_mm': height_mm,
        }

    return slots


# ── SVG ID Deduplication ─────────────────────────────────────────

def _deduplicate_svg_ids(svg_element, prefix: str):
    """Prefix all id= attributes and url(#...) references to avoid cross-panel collisions."""
    id_map: dict[str, str] = {}

    # Pass 1: collect and rename all id attributes
    for node in svg_element.iter():
        old_id = node.get('id')
        if old_id:
            new_id = f'{prefix}_{old_id}'
            id_map[old_id] = new_id
            node.set('id', new_id)

    if not id_map:
        return

    # Pass 2: update all url(#...) references in attributes
    def _rewrite_url_refs(text: str) -> str:
        def _sub(m):
            ref = m.group(1)
            return f'url(#{id_map.get(ref, ref)})'
        return URL_REF_RE.sub(_sub, text)

    href_attrs = ['href', f'{{{XLINK_NS}}}href']

    for node in svg_element.iter():
        for attr_name, attr_val in list(node.attrib.items()):
            if 'url(#' in attr_val:
                node.set(attr_name, _rewrite_url_refs(attr_val))
            if attr_name == 'clip-path' or attr_name == 'mask' or attr_name == 'filter':
                if 'url(#' in attr_val:
                    node.set(attr_name, _rewrite_url_refs(attr_val))

        # Update href="#id" references (e.g., <use href="#symbol">)
        for href_attr in href_attrs:
            href_val = node.get(href_attr)
            if href_val and href_val.startswith('#'):
                ref = href_val[1:]
                if ref in id_map:
                    node.set(href_attr, f'#{id_map[ref]}')

        # Update style attributes containing url(#...)
        style = node.get('style', '')
        if 'url(#' in style:
            node.set('style', _rewrite_url_refs(style))


# ── Font Compensation ────────────────────────────────────────────

def _parse_font_size(value: str) -> tuple[float, str] | None:
    """Parse font-size value. Returns None for relative units (em, %, etc.)."""
    stripped = value.strip()
    for unit in ('pt', 'px', 'mm'):
        if stripped.endswith(unit):
            try:
                return float(stripped[:-len(unit)]), unit
            except ValueError:
                return None
    # Check for relative units — skip these
    for unit in RELATIVE_UNITS:
        if stripped.endswith(unit):
            return None
    try:
        return float(stripped), 'px'
    except ValueError:
        return None


def compensate_font_size(svg_root, scale: float):
    if abs(scale - 1.0) < 0.05:
        return

    inverse = 1.0 / scale

    for node in svg_root.iter(f'{{{SVG_NS}}}text', f'{{{SVG_NS}}}tspan'):
        fs_attr = node.get('font-size')
        if fs_attr:
            parsed = _parse_font_size(fs_attr)
            if parsed:
                val, unit = parsed
                node.set('font-size', f'{val * inverse:.2f}{unit}')

        style = node.get('style', '')
        if 'font-size' in style:
            def _replace(m):
                val = float(m.group(1))
                unit = m.group(2) or 'px'
                return f'font-size: {val * inverse:.2f}{unit}'
            node.set('style', FONT_SIZE_RE.sub(_replace, style))


def sanitize_svg(svg_root):
    """Convert CSS shorthand properties to explicit SVG attributes for journal compatibility."""
    for node in svg_root.iter():
        style = node.get('style', '')
        if not style:
            continue

        # Parse CSS shorthand 'font:' into explicit properties
        font_match = FONT_SHORTHAND_RE.search(style)
        if font_match:
            font_size_val = font_match.group(1)
            font_family_val = font_match.group(2).strip().rstrip(';')
            # Remove the shorthand from style
            style = FONT_SHORTHAND_RE.sub('', style)
            # Set explicit attributes (only if not already set)
            if not node.get('font-size'):
                node.set('font-size', font_size_val)
            if not node.get('font-family'):
                node.set('font-family', font_family_val)

        # Extract key CSS properties from style into SVG attributes
        css_to_attr = {
            'fill': CSS_FILL_RE,
            'stroke': CSS_STROKE_RE,
            'stroke-width': CSS_STROKE_WIDTH_RE,
            'opacity': CSS_OPACITY_RE,
        }

        for attr_name, pattern in css_to_attr.items():
            match = pattern.search(style)
            if match and not node.get(attr_name):
                node.set(attr_name, match.group(1).strip())

        # Clean up empty/whitespace-only style attributes
        cleaned = style.strip().rstrip(';').strip()
        if cleaned:
            node.set('style', cleaned)
        elif 'style' in node.attrib:
            del node.attrib['style']


# ── Raster Embedding ─────────────────────────────────────────────

def _is_raster(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RASTER_EXTENSIONS


def _embed_raster_as_svg(src_path: str, slot_w_px: float, slot_h_px: float) -> sg.FigureElement:
    """Embed raster as SVG <image>, preserving aspect ratio within slot bounds."""
    from PIL import Image
    try:
        with Image.open(src_path) as img:
            img_w, img_h = img.size
    except Exception:
        img_w, img_h = 1, 1

    # Fit within slot preserving aspect ratio
    img_aspect = img_w / img_h if img_h > 0 else 1.0
    slot_aspect = slot_w_px / slot_h_px if slot_h_px > 0 else 1.0

    if img_aspect > slot_aspect:
        render_w = slot_w_px
        render_h = slot_w_px / img_aspect
    else:
        render_h = slot_h_px
        render_w = slot_h_px * img_aspect

    # Center within slot
    offset_x = (slot_w_px - render_w) / 2
    offset_y = (slot_h_px - render_h) / 2

    mime, _ = mimetypes.guess_type(src_path)
    if mime is None:
        mime = 'image/png'
    with open(src_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')
    img_el = etree.Element(f'{{{SVG_NS}}}image', {
        'x': f'{offset_x:.1f}',
        'y': f'{offset_y:.1f}',
        'width': f'{render_w:.1f}',
        'height': f'{render_h:.1f}',
        f'{{{XLINK_NS}}}href': f'data:{mime};base64,{data}',
    })
    return sg.FigureElement(img_el)


# ── Main Assembly ────────────────────────────────────────────────

def _read_svg_native_width_mm(svg_path: str) -> float:
    doc = sg.fromfile(svg_path)
    width_str = doc.width
    if width_str is None:
        return 100.0
    w = str(width_str).strip()
    if w.endswith('mm'):
        return float(w[:-2])
    if w.endswith('pt'):
        return float(w[:-2]) * 0.352778
    if w.endswith('in'):
        return float(w[:-2]) * 25.4
    # Handle relative/unknown units — fall back to 100mm
    cleaned = w.replace('px', '')
    try:
        return float(cleaned) / MM_TO_PX
    except ValueError:
        return 100.0


def assemble_figure(fig_id: str, fig_cfg: dict, project_dir: str) -> str:
    target_width = fig_cfg.get('target_width_mm', 183)
    gap = fig_cfg.get('gap_mm', 3)
    layout_str = fig_cfg['layout']
    panels_cfg = fig_cfg.get('panels', {})
    row_ratios = fig_cfg.get('row_height_ratios')

    grid = parse_layout(layout_str)

    # Validate contiguous rectangles
    contiguous_errors = validate_layout_contiguous(grid)
    if contiguous_errors:
        raise ValueError(f"Invalid layout for {fig_id}: {'; '.join(contiguous_errors)}")

    slots = compute_slots(grid, target_width, gap, row_ratios)

    max_bottom = max(s['y_mm'] + s['height_mm'] for s in slots.values())
    canvas_w_px = target_width * MM_TO_PX
    canvas_h_px = max_bottom * MM_TO_PX

    fig = sg.SVGFigure(f'{canvas_w_px}', f'{canvas_h_px}')

    merged_elements = []

    for panel_id, slot in slots.items():
        p_cfg = panels_cfg.get(panel_id)
        if p_cfg is None:
            continue

        src_path = os.path.join(project_dir, p_cfg['source'])
        if not os.path.exists(src_path):
            raise FileNotFoundError(f'Source panel not found: {src_path}')

        font_strategy = p_cfg.get('font_strategy', 'compensate')
        x_px = slot['x_mm'] * MM_TO_PX
        y_px = slot['y_mm'] * MM_TO_PX
        slot_w_px = slot['width_mm'] * MM_TO_PX
        slot_h_px = slot['height_mm'] * MM_TO_PX

        # Generate unique prefix for SVG ID deduplication
        id_prefix = f'p{panel_id}_{uuid.uuid4().hex[:6]}'

        if _is_raster(src_path):
            img_el = _embed_raster_as_svg(src_path, slot_w_px, slot_h_px)
            group = sg.GroupElement([img_el])
            group.moveto(x_px, y_px)
            merged_elements.append(group)
        else:
            panel_svg = sg.fromfile(src_path)
            panel_root = panel_svg.getroot()
            native_width = _read_svg_native_width_mm(src_path)
            scale = slot['width_mm'] / native_width if native_width > 0 else 1.0

            # Fix 1: Deduplicate SVG IDs to prevent cross-panel collisions
            _deduplicate_svg_ids(panel_root.root, id_prefix)

            if font_strategy == 'compensate':
                compensate_font_size(panel_root.root, scale)

            group = sg.GroupElement([panel_root])
            group.moveto(x_px, y_px, scale)
            merged_elements.append(group)

        tag_text = f'({panel_id})'
        tag_x_px = (slot['x_mm'] + 1.5) * MM_TO_PX
        tag_y_px = (slot['y_mm'] + 4) * MM_TO_PX
        text_el = etree.Element(f'{{{SVG_NS}}}text', {
            'x': f'{tag_x_px:.1f}',
            'y': f'{tag_y_px:.1f}',
            'font-family': 'Arial, Helvetica, sans-serif',
            'font-weight': 'bold',
            'font-size': f'{TAG_FONT_SIZE_PT}pt',
            'fill': 'black',
        })
        text_el.text = tag_text
        merged_elements.append(sg.FigureElement(text_el))

    fig.append(merged_elements)

    out_dir = os.path.join(project_dir, 'results', 'final')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{fig_id}.svg')
    # Sanitize CSS for journal submission compatibility
    sanitize_svg(fig.root)
    fig.save(out_path)
    return out_path
