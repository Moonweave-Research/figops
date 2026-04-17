"""
Graph Hub -- Batch journal format conversion.

Re-renders all figures in a project for a different target journal
with a single command, patching visual_style.target_format in the config.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from pathlib import Path

from hub_core.config_parser import ALLOWED_TARGET_FORMATS


@dataclass
class BatchReformatResult:
    target_journal: str
    figures_regenerated: int
    output_paths: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    success: bool = False
    error: str = ""


def patch_target_format(config: dict, target_format: str) -> dict:
    """Deep-copy config and override all format-related fields."""
    if target_format not in ALLOWED_TARGET_FORMATS:
        allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
        raise ValueError(f"Unknown target format '{target_format}'. Allowed: {allowed}")

    patched = copy.deepcopy(config)

    # Override top-level visual_style
    vs = patched.setdefault("visual_style", {})
    vs["target_format"] = target_format

    # Override any per-figure theme overrides
    for fig in patched.get("figures", []):
        if "theme" in fig:
            fig["theme"] = target_format

    # Override preset defaults
    for preset_name, preset_vals in patched.get("presets", {}).items():
        if isinstance(preset_vals, dict) and "target_format" in preset_vals:
            preset_vals["target_format"] = target_format

    return patched


def batch_reformat_figures(
    project_dir: str,
    target_journal: str,
    config: dict,
    hub_path: str,
    *,
    force: bool = True,
) -> BatchReformatResult:
    """Re-render all figures for a different target journal.

    Patches the config's target_format, then runs the plot step with force=True.
    """
    start = time.monotonic()

    try:
        patched_config = patch_target_format(config, target_journal)
    except ValueError as exc:
        return BatchReformatResult(
            target_journal=target_journal,
            figures_regenerated=0,
            error=str(exc),
        )

    figure_count = len(patched_config.get("figures", []))
    if figure_count == 0:
        return BatchReformatResult(
            target_journal=target_journal,
            figures_regenerated=0,
            success=True,
            elapsed_seconds=time.monotonic() - start,
        )

    # Import here to avoid circular deps
    from hub_core.cache_manager import load_build_state
    from hub_core.config_parser import compute_config_hash
    from hub_core.process_runner import run_plots

    project_path = Path(project_dir).resolve()
    build_state_path = project_path / ".build_state.json"
    build_state = load_build_state(build_state_path)
    config_hash = compute_config_hash(patched_config)

    success = run_plots(
        str(project_path),
        patched_config,
        build_state=build_state,
        build_state_path=str(build_state_path),
        config_hash=config_hash,
        force=force,
    )

    # Collect output paths
    output_paths: list[str] = []
    for fig in patched_config.get("figures", []):
        output = fig.get("output", "")
        if output:
            full_path = project_path / output
            if full_path.exists():
                output_paths.append(str(full_path))

    elapsed = time.monotonic() - start
    return BatchReformatResult(
        target_journal=target_journal,
        figures_regenerated=len(output_paths),
        output_paths=output_paths,
        elapsed_seconds=round(elapsed, 2),
        success=success,
    )
