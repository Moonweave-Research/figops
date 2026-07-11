"""Validation for declarative multi-panel figure assembly configuration."""

from __future__ import annotations

import os


def validate_assemblies(errors: list[str], assemblies, *, allowed_font_strategies) -> None:
    """Append all assembly-schema errors without changing their established text."""
    if assemblies is None:
        return
    if not isinstance(assemblies, dict):
        errors.append("Invalid 'assemblies' section (must be a mapping).")
        return

    for fig_id, fig_cfg in assemblies.items():
        if not isinstance(fig_cfg, dict):
            errors.append(f"assemblies.{fig_id} must be a mapping.")
            continue

        target_width = fig_cfg.get("target_width_mm")
        if target_width is None:
            errors.append(f"assemblies.{fig_id}.target_width_mm is required.")
        elif not isinstance(target_width, (int, float)) or target_width <= 0:
            errors.append(f"assemblies.{fig_id}.target_width_mm must be a positive number.")

        gap = fig_cfg.get("gap_mm", 3)
        if not isinstance(gap, (int, float)) or gap < 0:
            errors.append(f"assemblies.{fig_id}.gap_mm must be a non-negative number.")

        layout = fig_cfg.get("layout")
        if not isinstance(layout, str) or not layout.strip():
            errors.append(f"assemblies.{fig_id}.layout is required (mosaic string).")
        else:
            rows = [list(row) for row in layout.strip().splitlines() if row.strip()]
            if rows:
                row_length = len(rows[0])
                for row_index, row in enumerate(rows):
                    if len(row) != row_length:
                        errors.append(
                            f"assemblies.{fig_id}.layout row {row_index + 1} has {len(row)} cols, "
                            f"expected {row_length}."
                        )

                chars: dict[str, list[tuple[int, int]]] = {}
                for row_index, row in enumerate(rows):
                    for column_index, char in enumerate(row):
                        if char != ".":
                            chars.setdefault(char, []).append((row_index, column_index))
                for char, cells in chars.items():
                    rows_set = {row for row, _ in cells}
                    cols_set = {column for _, column in cells}
                    if len(cells) != len(rows_set) * len(cols_set):
                        errors.append(
                            f"assemblies.{fig_id}.layout: character '{char}' does not form a contiguous rectangle."
                        )

        row_height_ratios = fig_cfg.get("row_height_ratios")
        if row_height_ratios is not None:
            if not isinstance(row_height_ratios, list):
                errors.append(f"assemblies.{fig_id}.row_height_ratios must be a list.")
            elif isinstance(layout, str) and layout.strip():
                layout_row_count = len([row for row in layout.strip().splitlines() if row.strip()])
                if len(row_height_ratios) != layout_row_count:
                    errors.append(
                        f"assemblies.{fig_id}.row_height_ratios has {len(row_height_ratios)} entries "
                        f"but layout has {layout_row_count} rows."
                    )

        panels = fig_cfg.get("panels", {})
        if not isinstance(panels, dict):
            errors.append(f"assemblies.{fig_id}.panels must be a mapping.")
            continue

        for panel_id, panel_config in panels.items():
            if not isinstance(panel_config, dict):
                errors.append(f"assemblies.{fig_id}.panels.{panel_id} must be a mapping.")
                continue
            if "source" not in panel_config or not isinstance(panel_config["source"], str):
                errors.append(f"assemblies.{fig_id}.panels.{panel_id}.source is required (string).")
            else:
                source = panel_config["source"]
                if os.path.isabs(source):
                    errors.append(f"assemblies.{fig_id}.panels.{panel_id}.source: absolute paths are not allowed.")
                elif ".." in source.replace("\\", "/").split("/"):
                    errors.append(f"assemblies.{fig_id}.panels.{panel_id}.source: path traversal '..' is not allowed.")
            font_strategy = panel_config.get("font_strategy", "compensate")
            if font_strategy not in allowed_font_strategies:
                allowed = ", ".join(sorted(allowed_font_strategies))
                errors.append(f"assemblies.{fig_id}.panels.{panel_id}.font_strategy must be one of: {allowed}.")

        if isinstance(layout, str) and layout.strip():
            layout_chars = {char for row in rows for char in row if char != "."}
            panel_keys = set(panels.keys())
            missing_panels = layout_chars - panel_keys
            extra_panels = panel_keys - layout_chars
            if missing_panels:
                errors.append(
                    f"assemblies.{fig_id}: layout references "
                    f"{sorted(missing_panels)} but panels section is missing them."
                )
            if extra_panels:
                errors.append(
                    f"assemblies.{fig_id}: panels {sorted(extra_panels)} are not referenced in layout."
                )
