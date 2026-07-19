import os
from pathlib import Path

DEFAULT_CONFIG_TEMPLATE = "project_config_template.yaml"
TEMPLATE_PACKAGE_DIR = Path("hub_core") / "templates"
DEFAULT_WIZARD_TARGET_FORMAT = "nature"

DEFAULT_RAW_CSV = """time,value,molarity
0.0,1.0,0.1
1.0,1.4,0.1
2.0,1.9,0.2
"""

DEFAULT_ANALYZE_R = """suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
})

output_dir <- file.path(getwd(), "results", "data", "source")
output_path <- file.path(output_dir, "summary.csv")

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

input_env <- Sys.getenv("GRAPH_HUB_INPUTS", unset = "")
input_entries <- character()
if (nzchar(input_env)) {
  input_entries <- strsplit(input_env, .Platform$path.sep, fixed = TRUE)[[1]]
  input_entries <- trimws(input_entries)
  input_entries <- input_entries[nzchar(input_entries)]
}

csv_files <- character()
if (length(input_entries) > 0) {
  for (entry in input_entries) {
    if (dir.exists(entry)) {
      csv_files <- c(csv_files, list.files(entry, pattern = "\\\\.csv$", full.names = TRUE, recursive = TRUE))
    } else if (file.exists(entry) && grepl("\\\\.csv$", entry, ignore.case = TRUE)) {
      csv_files <- c(csv_files, entry)
    }
  }
} else {
  raw_dir <- file.path(getwd(), "raw")
  if (dir.exists(raw_dir)) {
    csv_files <- list.files(raw_dir, pattern = "\\\\.csv$", full.names = TRUE, recursive = TRUE)
  }
}
csv_files <- unique(csv_files)

if (length(csv_files) == 0) {
  if (identical(Sys.getenv("GRAPH_HUB_ALLOW_EMPTY_ANALYSIS", unset = ""), "1")) {
    warning("GRAPH_HUB_ALLOW_EMPTY_ANALYSIS=1 set; writing empty bootstrap scaffold data.")
    summary_df <- tibble(
      time = c(0.0, 1.0, 2.0),
      value = c(0.0, 0.0, 0.0),
      molarity = c(0.0, 0.0, 0.0)
    )
  } else {
    stop("No analysis input CSV found. Set GRAPH_HUB_INPUTS or place CSV files under raw/.")
  }
} else {
  first_csv <- csv_files[[1]]
  summary_df <- read_csv(first_csv, show_col_types = FALSE)

  required_cols <- c("time", "value", "molarity")
  missing_cols <- setdiff(required_cols, names(summary_df))
  if (length(missing_cols) > 0) {
    stop(sprintf(
      "Missing required column(s) in %s: %s",
      basename(first_csv),
      paste(missing_cols, collapse = ", ")
    ))
  }

  summary_df <- summary_df %>%
    select(all_of(required_cols))
}

summary_df <- summary_df %>%
  mutate(
    across(
      all_of(c("time", "value", "molarity")),
      ~ format(as.numeric(.x), scientific = FALSE, trim = TRUE, nsmall = 1)
    )
  )

write_csv(summary_df, output_path)
message(sprintf("Wrote scaffold summary CSV: %s", output_path))
"""

DEFAULT_PROJECT_CONTEXT_PY = """import os
import sys


def setup_hub_path():
    hub_path = os.environ.get("RESEARCH_HUB_PATH")
    if not hub_path:
        raise RuntimeError("RESEARCH_HUB_PATH is required when running FigOps project scripts.")
    if hub_path not in sys.path:
        sys.path.insert(0, hub_path)
    return hub_path


setup_hub_path()

from themes.journal_theme import apply_journal_theme, font_tokens


def theme_font_tokens(target_format=None, font_scale=None, profile_name=None):
    target = target_format or os.environ.get("THEME_FORMAT", "neutral")
    scale = float(font_scale if font_scale is not None else os.environ.get("THEME_SCALE", "1.0"))
    profile = profile_name or os.environ.get("THEME_PROFILE", "baseline")
    return font_tokens(target, scale, profile)


def apply_project_theme(target_format=None, font_scale=None, profile_name=None):
    target = target_format or os.environ.get("THEME_FORMAT", "neutral")
    scale = float(font_scale if font_scale is not None else os.environ.get("THEME_SCALE", "1.0"))
    profile = profile_name or os.environ.get("THEME_PROFILE", "baseline")
    apply_journal_theme(target_format=target, font_scale=scale, profile_name=profile)
    return theme_font_tokens(target, scale, profile)
"""

DEFAULT_PLOT_PY = """import logging
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr, force=True)
logger = logging.getLogger(__name__)

hub_path = os.environ.get("RESEARCH_HUB_PATH")
if not hub_path:
    raise RuntimeError("RESEARCH_HUB_PATH is required when running this plot script outside FigOps.")
if hub_path not in sys.path:
    sys.path.insert(0, hub_path)

from themes.journal_theme import (
    SINGLE_COLUMN,
    apply_journal_theme,
    font_tokens,
    get_figsize,
    panel_label,
    save_journal_fig,
)


def main():
    target_format = os.environ.get("THEME_FORMAT", "neutral")
    font_scale = float(os.environ.get("THEME_SCALE", "1.0"))
    profile_name = os.environ.get("THEME_PROFILE", "baseline")

    apply_journal_theme(
        target_format=target_format,
        font_scale=font_scale,
        profile_name=profile_name,
    )
    FONT = font_tokens(target_format, font_scale)

    csv_path = os.path.join(os.getcwd(), "results", "data", "source", "summary.csv")
    output_path = os.path.join(os.getcwd(), "results", "figures", "Fig1.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = pd.read_csv(csv_path)

    width, height = get_figsize(SINGLE_COLUMN, ratio=0.72)
    fig, ax = plt.subplots(figsize=(width, height))
    ax.plot(df["time"], df["value"], marker="o", linewidth=1.0)
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.set_title("Scaffold Figure")
    panel_label(ax, "(a)", fontsize=FONT.tag)

    save_journal_fig(fig, output_path)  # dpi from apply_journal_theme rcParams
    plt.close(fig)
    logger.info("Saved scaffold figure: %s", output_path)


if __name__ == "__main__":
    main()
"""

DEFAULT_DIAGRAM_PY = """import logging
import os
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr, force=True)
logger = logging.getLogger(__name__)

hub_path = os.environ.get("RESEARCH_HUB_PATH")
if not hub_path:
    raise RuntimeError("RESEARCH_HUB_PATH is required when running this diagram script outside FigOps.")
if hub_path not in sys.path:
    sys.path.insert(0, hub_path)

from themes.journal_theme import apply_journal_theme, font_tokens, panel_label, save_journal_fig


def main():
    target_format = os.environ.get("THEME_FORMAT", "neutral")
    font_scale = float(os.environ.get("THEME_SCALE", "1.0"))
    profile_name = os.environ.get("THEME_PROFILE", "baseline")

    apply_journal_theme(
        target_format=target_format,
        font_scale=font_scale,
        profile_name=profile_name,
    )
    FONT = font_tokens(target_format, font_scale)

    output_path = os.path.join(os.getcwd(), "results", "figures", "device_cross_section.svg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(4.8, 2.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    layers = [
        (0.8, 0.8, 8.4, 0.6, "#b0b7c3", "Top electrode"),
        (0.8, 1.5, 8.4, 1.0, "#d9e7f5", "Active layer"),
        (0.8, 2.7, 8.4, 0.6, "#b0b7c3", "Bottom electrode"),
    ]
    for x, y, w, h, color, label in layers:
        rect = Rectangle((x, y), w, h, facecolor=color, edgecolor="black", linewidth=1.0)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=FONT.label)

    ax.text(0.8, 3.55, "Scaffold Device Cross Section", ha="left", va="bottom", fontsize=FONT.annot)

    save_journal_fig(fig, output_path)  # dpi from apply_journal_theme rcParams
    plt.close(fig)
    logger.info("Saved scaffold diagram: %s", output_path)


if __name__ == "__main__":
    main()
"""


def scaffold_project(
    project_dir,
    hub_path,
    project_name=None,
    overwrite=False,
    *,
    target_format="neutral",
    font_scale=1.0,
):
    """Create a project through the same canonical manifest path used by MCP."""

    from .adapters import select_adapters
    from .project_normalization import apply_scaffold_project, plan_scaffold_project

    project_path = Path(project_dir).expanduser().resolve()
    hub_root = Path(hub_path).expanduser().resolve()
    name = _normalize_project_name(project_name, project_path)
    manifest = plan_scaffold_project(
        project_root=project_path,
        hub_path=hub_root,
        project_name=name,
        target_format=target_format,
        template="standard",
        conventions=select_adapters({}).conventions,
        font_scale=font_scale,
    )
    try:
        applied = apply_scaffold_project(manifest, overwrite=overwrite)
    except FileExistsError as exc:
        raise RuntimeError(f"Scaffold aborted: {exc}") from exc

    config_path = project_path / "project_config.yaml"
    created_paths = [Path(path) for path in applied["created_paths"]]
    directory_entries = [
        project_path / entry["destination"]
        for entry in applied["manifest"]["entries"]
        if entry.get("kind") == "directory" and entry.get("status") == "created"
    ]
    file_entries = [
        project_path / entry["destination"]
        for entry in applied["manifest"]["entries"]
        if entry.get("kind") == "file" and entry.get("status") == "created"
    ]

    return {
        "project_dir": str(project_path),
        "project_name": name,
        "config_path": str(config_path),
        "created_dirs": [str(path) for path in directory_entries],
        "created_files": [str(path) for path in file_entries],
        "created_paths": [str(path) for path in created_paths],
        "modified_paths": applied["modified_paths"],
        "skipped_paths": applied["skipped_paths"],
        "manifest": applied["manifest"],
        "overwrite": overwrite,
    }


def scaffold_wizard(hub_path):
    """대화형 위저드를 통해 프로젝트를 생성합니다."""
    from .config_parser import PUBLIC_TARGET_FORMATS
    from .ui_utils import ui_panel, ui_print, ui_prompt
    from .utils import get_research_root

    ui_panel(
        "🏛️ [bold]Research Project Scaffolding Wizard[/bold]\nNew project configuration made easy.",
        title="Wizard",
    )

    project_name = ui_prompt("Enter Project Name", default="New Research Project")
    folder_name = ui_prompt(
        "Enter Target Directory Name (relative to research root)",
        default=project_name.replace(" ", "_").lower(),
    )

    research_root = get_research_root()
    target_dir = os.path.join(research_root, folder_name)

    if os.path.exists(target_dir) and any(Path(target_dir).iterdir()):
        ui_print("[yellow]Aborted: scaffolding never overwrites an existing project.[/yellow]")
        return None

    allowed_target_formats = sorted(PUBLIC_TARGET_FORMATS)
    target_format_input = ui_prompt(
        f"Journal Target Format ({', '.join(allowed_target_formats)})",
        default=DEFAULT_WIZARD_TARGET_FORMAT,
    )
    try:
        target_format = normalize_scaffold_target_format(target_format_input, allowed_target_formats)
    except ValueError as exc:
        ui_print(f"[red]Invalid target format:[/red] {exc}")
        return None
    font_scale = ui_prompt("Font Scale", default="1.0")

    res = scaffold_project(
        target_dir,
        hub_path,
        project_name=project_name,
        target_format=target_format,
        font_scale=float(font_scale),
    )

    ui_print(f"\n✅ [bold green]Project '{project_name}' successfully initialized![/bold green]")
    ui_print(f"   Location: {target_dir}")
    return res


def normalize_scaffold_target_format(target_format, allowed_target_formats=None):
    if allowed_target_formats is None:
        from .config_parser import ALLOWED_TARGET_FORMATS

        allowed_target_formats = ALLOWED_TARGET_FORMATS
    allowed = {str(value).strip().lower() for value in allowed_target_formats}
    normalized = str(target_format or "").strip().lower()
    if normalized not in allowed:
        allowed_display = ", ".join(sorted(allowed))
        raise ValueError(f"{target_format!r} is not supported. Allowed values: {allowed_display}.")
    return normalized


def _normalize_project_name(project_name, project_path):
    raw = project_name if isinstance(project_name, str) and project_name.strip() else project_path.name
    return raw.strip()


def load_config_template_text(hub_root):
    """Load the scaffold template from the requested source or installed hub root."""
    resolved_hub_root = Path(hub_root).expanduser().resolve()
    template_path = resolved_hub_root / DEFAULT_CONFIG_TEMPLATE
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")

    packaged_template_path = resolved_hub_root / TEMPLATE_PACKAGE_DIR / DEFAULT_CONFIG_TEMPLATE
    if packaged_template_path.exists():
        return packaged_template_path.read_text(encoding="utf-8")

    raise RuntimeError(f"Missing scaffold template: {template_path} or {packaged_template_path}")


def _render_config_template(template_text, project_name):
    return template_text.replace(
        'name: "Ionoelastomer Displacement Analysis"',
        f'name: "{project_name}"',
        1,
    ).replace(
        'name: "Example Study"',
        f'name: "{project_name}"',
        1,
    )


def _ensure_dir(path, created_paths):
    if path.exists():
        return
    path.mkdir(parents=True, exist_ok=True)
    created_paths.append(path)


def _write_text(path, content):
    path.write_text(content, encoding="utf-8")
