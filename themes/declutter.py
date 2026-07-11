"""Optional text decluttering for publication figures."""

from __future__ import annotations


def _declutter_text_artists(fig, *, max_iter: int = 24, step_px: float = 4.0) -> dict:
    """Opt-in, conservative text nudge pass for obvious text/marker overlaps."""
    from matplotlib.text import Text
    from matplotlib.transforms import Bbox

    try:
        from hub_core.geometry_diagnostics import (
            _artist_overlap_candidate_items,
            _box_vector_away,
            _marker_footprint_box_entries,
        )
        from plotting.utils import place_point_labels
    except Exception as exc:
        return {"enabled": True, "applied": False, "iterations": 0, "reason": str(exc)}

    axes = [axis for axis in fig.axes if axis.get_visible() and getattr(axis, "_graph_hub_role", None) != "colorbar"]
    moved = 0
    iterations = 0
    residual_overlap_pairs = 0
    for iterations in range(1, max_iter + 1):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        changed = False
        for ax in axes:
            candidates = _artist_overlap_candidate_items(ax, renderer)
            if not candidates:
                continue
            displacements: dict[Text, tuple[float, float]] = {}
            leader_texts: list[Text] = []
            leader_xs: list[float] = []
            leader_ys: list[float] = []
            marker_boxes = _marker_footprint_box_entries(ax, ax.figure)
            for text in ax.texts:
                if not isinstance(text, Text) or not text.get_text() or not text.get_visible():
                    continue
                if text.get_transform() is not ax.transData:
                    continue
                text_box = text.get_window_extent(renderer)
                if text_box is None or text_box.width <= 0 or text_box.height <= 0:
                    continue
                text_center_x = (text_box.x0 + text_box.x1) / 2
                text_center_y = (text_box.y0 + text_box.y1) / 2
                existing_target = getattr(text, "_graph_hub_leader_target_data", None)
                existing_target_px = None
                if isinstance(existing_target, (tuple, list)) and len(existing_target) == 2:
                    try:
                        existing_target_px = ax.transData.transform(
                            (float(existing_target[0]), float(existing_target[1]))
                        )
                    except (TypeError, ValueError):
                        existing_target_px = None
                best_marker_box = None
                best_score: tuple[float, float] | None = None
                for _marker_label, marker_box in marker_boxes:
                    inter = Bbox.intersection(text_box, marker_box)
                    if inter is None or inter.width <= 0 or inter.height <= 0:
                        continue
                    marker_center_x = (marker_box.x0 + marker_box.x1) / 2
                    marker_center_y = (marker_box.y0 + marker_box.y1) / 2
                    overlap_area = float(inter.width * inter.height)
                    distance_sq = (text_center_x - marker_center_x) ** 2 + (text_center_y - marker_center_y) ** 2
                    target_tiebreaker = bool(
                        existing_target_px is not None
                        and marker_box.x0 <= existing_target_px[0] <= marker_box.x1
                        and marker_box.y0 <= existing_target_px[1] <= marker_box.y1
                    )
                    score = (overlap_area, -distance_sq, float(target_tiebreaker))
                    if best_score is None or score > best_score:
                        best_marker_box = marker_box
                        best_score = score
                if best_marker_box is not None:
                    target_x, target_y = ax.transData.inverted().transform(
                        ((best_marker_box.x0 + best_marker_box.x1) / 2, (best_marker_box.y0 + best_marker_box.y1) / 2)
                    )
                    leader_texts.append(text)
                    leader_xs.append(float(target_x))
                    leader_ys.append(float(target_y))
            if leader_texts:
                place_point_labels(
                    ax,
                    leader_xs,
                    leader_ys,
                    [text.get_text() for text in leader_texts],
                    leader=True,
                    min_leader_distance_px=1.0,
                    existing_texts=leader_texts,
                )
                moved += len(leader_texts)
                changed = True
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                candidates = _artist_overlap_candidate_items(ax, renderer)
            for index_a in range(len(candidates)):
                _label_a, box_a, artist_a = candidates[index_a]
                for index_b in range(index_a + 1, len(candidates)):
                    _label_b, box_b, artist_b = candidates[index_b]
                    inter = Bbox.intersection(box_a, box_b)
                    if inter is None or inter.width <= 0 or inter.height <= 0:
                        continue
                    if (
                        isinstance(artist_a, Text)
                        and isinstance(artist_b, Text)
                        and artist_a.get_transform() is ax.transData
                        and artist_b.get_transform() is ax.transData
                    ):
                        center_a = ((box_a.x0 + box_a.x1) / 2, (box_a.y0 + box_a.y1) / 2)
                        center_b = ((box_b.x0 + box_b.x1) / 2, (box_b.y0 + box_b.y1) / 2)
                        if abs(center_a[0] - center_b[0]) <= 1.0 and abs(center_a[1] - center_b[1]) <= 1.0:
                            if inter.width <= inter.height:
                                dx, dy = float(inter.width / 2 + step_px), 0.0
                            else:
                                dx, dy = 0.0, float(inter.height / 2 + step_px)
                            old_dx, old_dy = displacements.get(artist_a, (0.0, 0.0))
                            displacements[artist_a] = (old_dx - dx, old_dy - dy)
                            old_dx, old_dy = displacements.get(artist_b, (0.0, 0.0))
                            displacements[artist_b] = (old_dx + dx, old_dy + dy)
                            continue
                    if isinstance(artist_a, Text) and artist_a.get_transform() is ax.transData:
                        dx, dy = _box_vector_away(box_a, box_b, step_px=step_px, seed=id(artist_a))
                        old_dx, old_dy = displacements.get(artist_a, (0.0, 0.0))
                        displacements[artist_a] = (old_dx + dx, old_dy + dy)
                    if isinstance(artist_b, Text) and artist_b.get_transform() is ax.transData:
                        dx, dy = _box_vector_away(box_b, box_a, step_px=step_px, seed=id(artist_b))
                        old_dx, old_dy = displacements.get(artist_b, (0.0, 0.0))
                        displacements[artist_b] = (old_dx + dx, old_dy + dy)
            margin_px = 6.0
            axes_box = ax.get_window_extent(renderer)
            for text in ax.texts:
                if not isinstance(text, Text) or not text.get_text() or not text.get_visible():
                    continue
                if text.get_transform() is not ax.transData:
                    continue
                box = text.get_window_extent(renderer)
                if box is None or box.width <= 0 or box.height <= 0:
                    continue
                dx = 0.0
                dy = 0.0
                if box.x0 < axes_box.x0 + margin_px:
                    dx += axes_box.x0 + margin_px - box.x0
                if box.x1 > axes_box.x1 - margin_px:
                    dx -= box.x1 - (axes_box.x1 - margin_px)
                if box.y0 < axes_box.y0 + margin_px:
                    dy += axes_box.y0 + margin_px - box.y0
                if box.y1 > axes_box.y1 - margin_px:
                    dy -= box.y1 - (axes_box.y1 - margin_px)
                if dx or dy:
                    old_dx, old_dy = displacements.get(text, (0.0, 0.0))
                    displacements[text] = (old_dx + dx, old_dy + dy)
            for text, (dx, dy) in displacements.items():
                x, y = text.get_position()
                try:
                    display_xy = text.get_transform().transform((x, y))
                    new_xy = text.get_transform().inverted().transform((display_xy[0] + dx, display_xy[1] + dy))
                except Exception:
                    continue
                text.set_position((float(new_xy[0]), float(new_xy[1])))
                moved += 1
                changed = True
        if not changed:
            break
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        candidates = _artist_overlap_candidate_items(ax, renderer)
        for index_a in range(len(candidates)):
            _label_a, box_a, _artist_a = candidates[index_a]
            for index_b in range(index_a + 1, len(candidates)):
                _label_b, box_b, _artist_b = candidates[index_b]
                inter = Bbox.intersection(box_a, box_b)
                if inter is not None and inter.width > 0 and inter.height > 0:
                    residual_overlap_pairs += 1
    return {
        "enabled": True,
        "applied": moved > 0,
        "iterations": int(iterations if moved else 0),
        "moved_text_artists": int(moved),
        "converged": residual_overlap_pairs == 0,
        "residual_overlap_pairs": int(residual_overlap_pairs),
    }
