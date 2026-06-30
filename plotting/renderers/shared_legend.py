"""Shared legend helpers for multipanel bridge figures."""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt


def normalized_shared_legend_options(spec: Any) -> dict[str, object]:
    raw_options = spec.shared_legend_options
    if raw_options in (None, {}, ()):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("shared_legend_options must be an object")
    allowed = {"title", "order", "ncol", "position"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"shared_legend_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("title") is not None:
        normalized["title"] = str(raw_options["title"])
    if raw_options.get("order") is not None:
        order = raw_options["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError("shared_legend_options.order must be an array of labels")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError("shared_legend_options.order must not contain duplicate labels")
        normalized["order"] = labels
    if raw_options.get("ncol") is not None:
        if isinstance(raw_options["ncol"], bool) or not isinstance(raw_options["ncol"], int):
            raise ValueError("shared_legend_options.ncol must be an integer")
        ncol = raw_options["ncol"]
        if ncol < 1 or ncol > 8:
            raise ValueError("shared_legend_options.ncol must be between 1 and 8")
        normalized["ncol"] = ncol
    position = str(raw_options.get("position") or "top").strip().lower()
    if position not in {"top", "bottom", "right"}:
        raise ValueError("shared_legend_options.position must be top, bottom, or right")
    normalized["position"] = position
    return normalized


def apply_shared_legend(fig: Any, spec: Any) -> None:
    if not spec.shared_legend:
        return
    options = normalized_shared_legend_options(spec)
    position = str(options.get("position") or "top")
    raw_entries: dict[str, tuple[object, str]] = {}
    label_entries: dict[str, tuple[object, str]] = {}
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        handles, labels = ax.get_legend_handles_labels()
        label_to_handle = {label: handle for handle, label in zip(handles, labels) if label and label != "_nolegend_"}
        for raw, label in getattr(ax, "_graph_hub_legend_entries", ()):
            if label in label_to_handle and raw not in raw_entries:
                raw_entries[str(raw)] = (label_to_handle[label], str(label))
        for label, handle in label_to_handle.items():
            label_entries.setdefault(str(label), (handle, str(label)))
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()

    entries = raw_entries or label_entries
    if not entries:
        return
    ordered_keys = tuple(options.get("order") or ())
    missing = [key for key in ordered_keys if key not in entries]
    if missing:
        raise ValueError(f"shared_legend_options.order contains unknown legend key(s): {', '.join(missing)}")
    ordered = [entries[key] for key in ordered_keys]
    seen = set(ordered_keys)
    ordered.extend(entry for key, entry in entries.items() if key not in seen)
    handles, labels = zip(*ordered, strict=True)
    kwargs: dict[str, object] = {
        "handles": list(handles),
        "labels": list(labels),
        "frameon": False,
        "fontsize": plt.rcParams.get("legend.fontsize", 7.0),
        "ncol": int(options.get("ncol") or min(max(len(labels), 1), 4)),
    }
    if options.get("title") is not None:
        kwargs["title"] = options["title"]
    layout_lock = getattr(fig, "_graph_hub_layout_lock", {})
    is_manuscript = isinstance(layout_lock, dict) and layout_lock.get("compose_mode") == "manuscript"
    if position == "bottom":
        bottom_anchor = max(float(layout_lock.get("panel_area_bottom", 0.04)) - 0.02, 0.02) if is_manuscript else 0.02
        kwargs.update({"loc": "upper center", "bbox_to_anchor": (0.5, bottom_anchor)})
        if not is_manuscript:
            fig.subplots_adjust(bottom=max(float(fig.subplotpars.bottom), 0.18))
    elif position == "right":
        kwargs["ncol"] = int(options["ncol"]) if "ncol" in options else 1
        right_anchor = float(layout_lock.get("panel_area_right", 0.84)) + 0.02 if is_manuscript else 0.99
        kwargs.update({"loc": "center left", "bbox_to_anchor": (right_anchor, 0.5)})
        if not is_manuscript:
            fig.subplots_adjust(right=min(float(fig.subplotpars.right), 0.82))
    else:
        top_anchor = min(float(layout_lock.get("panel_area_top", 0.96)) + 0.02, 0.98) if is_manuscript else 0.98
        kwargs.update({"loc": "lower center", "bbox_to_anchor": (0.5, top_anchor)})
        if not is_manuscript:
            fig.subplots_adjust(top=min(float(fig.subplotpars.top), 0.86))
    legend = fig.legend(**kwargs)
    setattr(legend, "_graph_hub_legend_placement", f"shared_{position}")
