from __future__ import annotations

import logging
import os
import sys

_HANDLER_MARKER = "_graph_hub_handler"


def _resolve_level(level: str | int | None, *, verbose: bool = False) -> int:
    if verbose:
        return logging.DEBUG
    raw_level = level if level is not None else os.environ.get("GRAPH_HUB_LOG_LEVEL", "WARNING")
    if isinstance(raw_level, int):
        return raw_level
    normalized = str(raw_level).strip().upper()
    if not normalized:
        return logging.WARNING
    numeric = logging.getLevelName(normalized)
    if isinstance(numeric, int):
        return numeric
    raise ValueError(f"Invalid log level: {raw_level!r}")


def configure_logging(level: str | int | None = None, *, verbose: bool = False) -> None:
    log_level = _resolve_level(level, verbose=verbose)
    root = logging.getLogger()
    root.setLevel(log_level)

    handler = next(
        (candidate for candidate in root.handlers if getattr(candidate, _HANDLER_MARKER, False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        setattr(handler, _HANDLER_MARKER, True)
        root.addHandler(handler)
    else:
        handler.setStream(sys.stderr)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(logging.Formatter("%(message)s"))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
