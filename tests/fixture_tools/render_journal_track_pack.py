from __future__ import annotations

import argparse
import html
import importlib
import json
import shutil
import sys
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parents[2]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))

FIXTURE_ROOT = HUB_ROOT / "tests" / "fixtures" / "journal_tracks"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _case_entries(manifest, requested_case: str):
    entries = manifest["fixture_classes"]
    if requested_case == "all":
        return entries
    selected = [entry for entry in entries if entry["id"] == requested_case]
    if not selected:
        raise SystemExit(f"unknown fixture case: {requested_case}")
    return selected


def _copy_artifact(source: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination.resolve())


def _render_fixture(server, fixture, track: str, output_dir: Path):
    arguments = dict(fixture["render_arguments"])
    arguments.update(
        {
            "data_path": str((FIXTURE_ROOT / fixture["csv_path"]).resolve()),
            "target_format": track,
            "profile": "baseline",
            "output_format": "png",
            "overwrite": True,
            "job_id": f"journal-{fixture['id']}-{track}",
        }
    )
    response = server.call_tool("figops.render_csv_graph", arguments)
    result = response["structuredContent"]
    stem = f"{fixture['id']}_{track}"
    output_path = Path(result["output_path"])
    manifest_path = Path(result["manifest_path"])
    result["fixture_class"] = fixture["id"]
    result["track"] = track
    result["copied_output_path"] = _copy_artifact(str(output_path), output_dir / output_path.name)
    result["copied_manifest_path"] = _copy_artifact(str(manifest_path), output_dir / f"{stem}_manifest.json")
    return result


def _write_contact_sheet(summary, contact_sheet: Path) -> None:
    cards = []
    base = contact_sheet.parent.resolve()
    for entry in summary["entries"]:
        image_path = Path(entry["copied_output_path"]).resolve()
        relative = image_path.relative_to(base).as_posix()
        caption = html.escape(f"{entry['fixture_class']} / {entry['track']} / {entry['status']}")
        cards.append(f"<figure><img src=\"{relative}\" alt=\"{caption}\"><figcaption>{caption}</figcaption></figure>")
    markup = (
        "<!doctype html><meta charset=\"utf-8\"><title>Journal track fixtures</title>"
        "<style>body{font-family:sans-serif;margin:24px}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}"
        "figure{margin:0;border:1px solid #ddd;padding:8px}"
        "img{max-width:100%;height:auto;display:block}"
        "figcaption{font-size:12px;margin-top:6px}</style>"
        f"<main>{''.join(cards)}</main>"
    )
    contact_sheet.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet.write_text(markup, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="all")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--contact-sheet")
    args = parser.parse_args()

    manifest = _read_json(MANIFEST_PATH)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mcp_module = importlib.import_module("hub_core.mcp")
    server = mcp_module.GraphHubMCPServer(
        research_root=HUB_ROOT,
        runtime_root=output_dir / "_runtime",
        write_tools_enabled=True,
    )
    entries = [
        _render_fixture(server, fixture, track, output_dir)
        for fixture in _case_entries(manifest, args.case)
        for track in manifest["public_tracks"]
    ]
    summary = {
        "schema_version": "journal_track_render_pack/1",
        "entries": entries,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if args.contact_sheet:
        _write_contact_sheet(summary, Path(args.contact_sheet).resolve())
    print(json.dumps({"entries": len(entries), "summary_path": str((output_dir / "summary.json").resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
