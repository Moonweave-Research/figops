import os
from pathlib import Path

DEFAULT_CONFIG_TEMPLATE = "project_config_template.yaml"

DEFAULT_RAW_CSV = """time,value,molarity
0.0,1.0,0.1
1.0,1.4,0.1
2.0,1.9,0.2
"""

DEFAULT_ANALYZE_R = """suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
})

output_dir <- file.path(getwd(), "results", "data")
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
        raise RuntimeError("RESEARCH_HUB_PATH is required when running Graph Hub project scripts.")
    if hub_path not in sys.path:
        sys.path.insert(0, hub_path)
    return hub_path


setup_hub_path()

from themes.journal_theme import apply_journal_theme, font_tokens


def theme_font_tokens(target_format=None, font_scale=None, profile_name=None):
    target = target_format or os.environ.get("THEME_FORMAT", "nature")
    scale = float(font_scale if font_scale is not None else os.environ.get("THEME_SCALE", "1.0"))
    profile = profile_name or os.environ.get("THEME_PROFILE", "baseline")
    return font_tokens(target, scale, profile)


def apply_project_theme(target_format=None, font_scale=None, profile_name=None):
    target = target_format or os.environ.get("THEME_FORMAT", "nature")
    scale = float(font_scale if font_scale is not None else os.environ.get("THEME_SCALE", "1.0"))
    profile = profile_name or os.environ.get("THEME_PROFILE", "baseline")
    apply_journal_theme(target_format=target, font_scale=scale, profile_name=profile)
    return theme_font_tokens(target, scale, profile)
"""

DEFAULT_PLOT_PY = """import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

hub_path = os.environ.get("RESEARCH_HUB_PATH")
if not hub_path:
    raise RuntimeError("RESEARCH_HUB_PATH is required when running this plot script outside Graph Hub.")
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
    target_format = os.environ.get("THEME_FORMAT", "nature")
    font_scale = float(os.environ.get("THEME_SCALE", "1.0"))
    profile_name = os.environ.get("THEME_PROFILE", "baseline")

    apply_journal_theme(
        target_format=target_format,
        font_scale=font_scale,
        profile_name=profile_name,
    )
    FONT = font_tokens(target_format, font_scale)

    csv_path = os.path.join(os.getcwd(), "results", "data", "summary.csv")
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
    print(f"Saved scaffold figure: {output_path}")


if __name__ == "__main__":
    main()
"""

DEFAULT_DIAGRAM_PY = """import os
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

hub_path = os.environ.get("RESEARCH_HUB_PATH")
if not hub_path:
    raise RuntimeError("RESEARCH_HUB_PATH is required when running this diagram script outside Graph Hub.")
if hub_path not in sys.path:
    sys.path.insert(0, hub_path)

from themes.journal_theme import apply_journal_theme, font_tokens, panel_label, save_journal_fig


def main():
    target_format = os.environ.get("THEME_FORMAT", "nature")
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
    print(f"Saved scaffold diagram: {output_path}")


if __name__ == "__main__":
    main()
"""


def scaffold_project(project_dir, hub_path, project_name=None, overwrite=False):
    project_path = Path(project_dir).expanduser().resolve()
    hub_root = Path(hub_path).expanduser().resolve()

    template_path = hub_root / DEFAULT_CONFIG_TEMPLATE
    if not template_path.exists():
        raise RuntimeError(f"Missing scaffold template: {template_path}")

    config_path = project_path / "project_config.yaml"
    if config_path.exists() and not overwrite:
        raise RuntimeError(f"Scaffold aborted: config already exists: {config_path}")

    name = _normalize_project_name(project_name, project_path)
    config_text = _render_config_template(template_path, name)

    created_paths = []
    _ensure_dir(project_path, created_paths)

    required_dirs = [
        project_path / "raw",
        project_path / "results" / "data",
        project_path / "results" / "figures",
        project_path / "hub_scripts",
        project_path / "hub_scripts" / "diagrams",
    ]
    for path in required_dirs:
        _ensure_dir(path, created_paths)

    _write_text(config_path, config_text)
    _write_text(project_path / "raw" / "example_input.csv", DEFAULT_RAW_CSV)
    _write_text(project_path / "hub_scripts" / "analyze.R", DEFAULT_ANALYZE_R)
    _write_text(project_path / "hub_scripts" / "project_context.py", DEFAULT_PROJECT_CONTEXT_PY)
    _write_text(project_path / "hub_scripts" / "plot.py", DEFAULT_PLOT_PY)
    _write_text(project_path / "hub_scripts" / "diagrams" / "device_cross_section.py", DEFAULT_DIAGRAM_PY)

    return {
        "project_dir": str(project_path),
        "project_name": name,
        "config_path": str(config_path),
        "created_dirs": [str(path) for path in created_paths],
        "created_files": [
            str(config_path),
            str(project_path / "raw" / "example_input.csv"),
            str(project_path / "hub_scripts" / "analyze.R"),
            str(project_path / "hub_scripts" / "project_context.py"),
            str(project_path / "hub_scripts" / "plot.py"),
            str(project_path / "hub_scripts" / "diagrams" / "device_cross_section.py"),
        ],
        "overwrite": overwrite,
    }


def scaffold_wizard(hub_path):
    """대화형 위저드를 통해 프로젝트를 생성합니다."""
    from .ui_utils import ui_confirm, ui_panel, ui_print, ui_prompt
    from .utils import get_research_root

    ui_panel("🏛️ [bold]Research Project Scaffolding Wizard[/bold]\nNew project configuration made easy.", title="Wizard")

    project_name = ui_prompt("Enter Project Name", default="New Research Project")
    folder_name = ui_prompt(
        "Enter Target Directory Name (relative to research root)",
        default=project_name.replace(" ", "_").lower(),
    )

    research_root = get_research_root()
    target_dir = os.path.join(research_root, folder_name)

    if os.path.exists(target_dir):
        if not ui_confirm(f"Directory '{folder_name}' already exists. Overwrite?"):
            ui_print("[yellow]Aborted.[/yellow]")
            return None

    # YAML 구성 자동화
    target_format = ui_prompt("Journal Target Format (nature/nature_surfur/science/ppt)", default="nature")
    font_scale = ui_prompt("Font Scale", default="1.0")

    res = scaffold_project(target_dir, hub_path, project_name=project_name, overwrite=True)

    # 생성된 config 수정
    import yaml
    with open(res["config_path"], 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    config['project']['name'] = project_name
    config['visual_style']['target_format'] = target_format
    config['visual_style']['font_scale'] = float(font_scale)

    with open(res["config_path"], 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)

    ui_print(f"\n✅ [bold green]Project '{project_name}' successfully initialized![/bold green]")
    ui_print(f"   Location: {target_dir}")
    return res


def _normalize_project_name(project_name, project_path):
    raw = project_name if isinstance(project_name, str) and project_name.strip() else project_path.name
    return raw.strip()


def _render_config_template(template_path, project_name):
    template_text = template_path.read_text(encoding="utf-8")
    return template_text.replace(
        'name: "Ionoelastomer Displacement Analysis"',
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
