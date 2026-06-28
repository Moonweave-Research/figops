from pathlib import Path

from scripts.architecture_inventory import (
    architecture_inventory,
    render_architecture_inventory_markdown,
)

HUB_ROOT = Path(__file__).resolve().parent.parent


def test_architecture_inventory_reports_large_modules_in_descending_order():
    rows = architecture_inventory(HUB_ROOT)

    assert rows
    assert all(row["lines"] > 800 for row in rows)
    assert [row["lines"] for row in rows] == sorted((row["lines"] for row in rows), reverse=True)
    assert any(row["file"] == "plotting/bridge_renderer.py" for row in rows)


def test_architecture_inventory_matches_committed_architecture_doc():
    docs_text = (HUB_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    start = "<!-- architecture-inventory:start -->"
    end = "<!-- architecture-inventory:end -->"
    assert start in docs_text
    assert end in docs_text
    committed_block = docs_text.split(start, 1)[1].split(end, 1)[0].strip()

    expected_block = render_architecture_inventory_markdown(architecture_inventory(HUB_ROOT))

    assert committed_block == expected_block
