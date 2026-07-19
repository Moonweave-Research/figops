"""Safe lexical-path handling for discovered project configuration files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .project_paths import ProjectPathError, resolve_project_input


def resolve_discovered_config_path(
    project_dir,
    config_path,
    *,
    candidates: Iterable[str],
) -> Path:
    """Revalidate a discovered config without discarding its relative parent."""
    project_root = Path(project_dir).expanduser().absolute()
    lexical_config = Path(config_path).expanduser()
    if not lexical_config.is_absolute():
        lexical_config = project_root / lexical_config
    lexical_config = lexical_config.absolute()
    try:
        relative_config = lexical_config.relative_to(project_root).as_posix()
    except ValueError as exc:
        raise ProjectPathError("project config path escapes the lexical project root.") from exc

    supported_candidates = {Path(candidate).as_posix() for candidate in candidates}
    if relative_config not in supported_candidates:
        raise ProjectPathError(f"project config path is not a supported candidate: {relative_config!r}.")
    return resolve_project_input(
        project_dir,
        relative_config,
        purpose="project config",
    )
