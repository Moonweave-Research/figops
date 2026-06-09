from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import quote

PANELS = {
    "a": {
        "source": Path("assets/panel_response.svg"),
        "x": 10,
        "y": 12,
        "width": 105,
        "height": 72,
    },
    "b": {
        "source": Path("assets/panel_distribution.svg"),
        "x": 124,
        "y": 12,
        "width": 58,
        "height": 32,
    },
    "c": {
        "source": Path("assets/panel_summary.svg"),
        "x": 124,
        "y": 54,
        "width": 58,
        "height": 32,
    },
}


def _svg_data_uri(path: Path) -> str:
    payload = path.read_text(encoding="utf-8")
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def main() -> None:
    output = Path("results/figures/FigSynthetic_Multipanel.svg")
    output.parent.mkdir(parents=True, exist_ok=True)

    parts = [
        '<svg width="183mm" height="95mm" viewBox="0 0 183 95" xmlns="http://www.w3.org/2000/svg">',
        '<rect x="0" y="0" width="183" height="95" fill="#ffffff"/>',
    ]
    for label, panel in PANELS.items():
        x = panel["x"]
        y = panel["y"]
        parts.append(
            f'<text x="{x}" y="{y - 4}" font-size="7" font-weight="bold" '
            f'font-family="Arial, Helvetica, sans-serif">({quote(label)})</text>'
        )
        parts.append(
            f'<image x="{x}" y="{y}" width="{panel["width"]}" height="{panel["height"]}" '
            f'href="{_svg_data_uri(panel["source"])}"/>'
        )
    parts.append("</svg>")
    output.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
