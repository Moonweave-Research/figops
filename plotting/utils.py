"""
[Graph_making_hub]/plotting/utils.py
===================================
🔧 시각화 유틸리티 함수 (Reusable Visualization Helpers)

[역할 / Role]
- 논문용 그래프 작성 시 반복되는 텍스트 처리 및 레이아웃 최적화 로직 제공
- 샘플 라벨 축약, 범례 위치 최적화 등 "세밀한 한 끗"을 자동화

[주요 함수 / Key Functions]
- compress_sample_label: 지저분한 샘플명을 논문 규격으로 축약
- get_standard_legend_props: 소형 피규어(89mm)에 최적화된 범례 속성 반환
"""

from collections.abc import Sequence
from hashlib import sha256

import matplotlib.pyplot as plt


def normalize_label_map(raw: dict[str, str] | None) -> dict[str, str]:
    """Validate and copy an exact original-to-display label map."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("label_map must be an object mapping original labels to display labels")
    normalized: dict[str, str] = {}
    for original, display in raw.items():
        if not isinstance(original, str) or not original:
            raise ValueError("label_map keys must be non-empty strings")
        if not isinstance(display, str) or not display:
            raise ValueError(f"label_map[{original!r}] must be a non-empty string")
        normalized[original] = display
    return normalized


def label_transformation_evidence(
    values: Sequence[object],
    *,
    label_map: dict[str, str] | None = None,
    label_transform: str = "raw",
    compress_labels: bool = False,
) -> dict[str, object]:
    """Build deterministic mapping, collision, and mutation-ledger evidence."""
    mapping = normalize_label_map(label_map)
    transform = str(label_transform or "raw").strip().lower().replace("-", "_")
    if transform not in {"raw", "legacy_compress"}:
        raise ValueError("label_transform must be 'raw' or 'legacy_compress'")
    effective_transform = "legacy_compress" if compress_labels or transform == "legacy_compress" else "raw"

    seen: set[str] = set()
    records: list[dict[str, str]] = []
    displays: dict[str, list[str]] = {}
    ledger: list[dict[str, str]] = []
    for value in values:
        original = str(value)
        if original in seen:
            continue
        seen.add(original)
        if original in mapping:
            display = mapping[original]
            applied_transform = "label_map"
        elif effective_transform == "legacy_compress":
            display = compress_sample_label(original)
            applied_transform = "legacy_compress"
        else:
            display = original
            applied_transform = "raw"
        records.append({"original": original, "display": display, "transform": applied_transform})
        displays.setdefault(display, []).append(original)
        if display != original:
            digest = sha256(f"{applied_transform}\0{original}\0{display}".encode("utf-8")).hexdigest()[:16]
            ledger.append(
                {
                    "mutation_id": f"label-{digest}",
                    "transform": applied_transform,
                    "mode": "explicit" if applied_transform == "label_map" else "legacy_opt_in",
                    "before": original,
                    "after": display,
                    "policy_id": "authored-labels/1",
                    "reason": (
                        "explicit label_map"
                        if applied_transform == "label_map"
                        else "legacy reproduction requested"
                    ),
                }
            )
    collisions = [
        {"display": display, "originals": originals}
        for display, originals in sorted(displays.items())
        if len(originals) > 1
    ]
    return {
        "mode": effective_transform,
        "mappings": records,
        "collisions": collisions,
        "mutation_ledger": ledger,
    }


def add_smart_inset(ax, position="upper_right", size=0.3, padding=0.05, label_scale=0.8):
    """
    선언적으로 인셋(Inset)을 추가합니다.
    메인 축의 폰트 크기보다 작게(기본 0.8배) 자동 조정됩니다.
    """
    # [0, 0, 1, 1] 비율 좌표계에서의 위치 계산
    presets = {
        "upper_right": [1 - size - padding, 1 - size - padding, size, size],
        "upper_left": [padding, 1 - size - padding, size, size],
        "lower_right": [1 - size - padding, padding, size, size],
        "lower_left": [padding, padding, size, size],
    }

    rect = presets.get(position, presets["upper_right"])
    inset_ax = ax.inset_axes(rect)

    # 폰트 스케일링 설정 (Matplotlib은 수동 폰트 조정이 필요하므로, 이후 테마 적용 시 활용 가능)
    # 여기서는 간단히 축 라벨 크기 조정을 시연
    inset_ax.tick_params(labelsize=plt.rcParams["font.size"] * label_scale)

    return inset_ax


def auto_panel_tag(ax, label="a", x_offset=-0.08, y_offset=1.12):
    """
    패널 식별자(a, b, c)를 표준화된 위치(Top-left)에 배치합니다.
    여백을 조금 더 주어(y_offset=1.12) 타이틀과 겹침을 방지합니다.
    """
    ax.text(
        x_offset,
        y_offset,
        f"{label})",
        transform=ax.transAxes,
        fontsize=plt.rcParams["axes.titlesize"],
        fontweight="bold",
        va="bottom",
        ha="right",
    )


def apply_density_alpha(dataset_size, base_alpha=0.6, base_size=10):
    """
    데이터 밀도에 따라 점의 투명도와 크기를 자동으로 조절하여 뭉침을 방지합니다.
    """
    if dataset_size > 1000:
        alpha = base_alpha * 0.4
        size = base_size * 0.5
    elif dataset_size > 100:
        alpha = base_alpha * 0.7
        size = base_size * 0.8
    else:
        alpha = base_alpha
        size = base_size

    return alpha, size


def compress_sample_label(label: str) -> str:
    """
    지저분한 샘플 이름을 논문용으로 깔끔하게 축약합니다.
    (예: "Coated Sample_Noa_None_Aligned" -> "Coated, Noa, None, Aln.")
    """
    if not isinstance(label, str):
        return str(label)

    replacements = {
        "Coated Sample_": "Coated, ",
        " Removed": " Rem.",
        " + ": "+",
        "_": ", ",
        "Aligned": "Aln.",
        "Unaligned": "Unaln.",
        "None": "None",
        "None, None": "None",
    }

    compressed = label
    for old, new in replacements.items():
        compressed = compressed.replace(old, new)

    # 중복 쉼표 및 공백 정리
    compressed = compressed.replace(", ,", ",").strip(", ")
    return compressed


def place_point_labels(
    ax,
    xs: Sequence[float],
    ys: Sequence[float],
    texts: Sequence[str],
    *,
    leader: bool = True,
    min_leader_distance_px: float = 8.0,
    initial_offset_px: float = 10.0,
    fontsize: float | None = None,
    color: str = "black",
    leader_color: str = "0.35",
    leader_lw: float = 0.6,
    bbox: dict | None = None,
    adjust_kwargs: dict | None = None,
    existing_texts: Sequence | None = None,
):
    """Place point labels in free space and optionally draw leader lines.

    The helper marks each label with ``_graph_hub_leader_target_data`` so geometry
    diagnostics can distinguish intentional leader-connected labels from accidental
    text-marker collisions.
    """
    from adjustText import adjust_text

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer)
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x_per_px = (xlim[1] - xlim[0]) / max(float(axes_box.width), 1.0)
    y_per_px = (ylim[1] - ylim[0]) / max(float(axes_box.height), 1.0)
    directions = ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (1, 0), (0, -1), (-1, 0))

    label_artists = []
    target_x = []
    target_y = []
    default_bbox = {"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.2}
    label_bbox = default_bbox if bbox is None else bbox
    for index, (x, y, label) in enumerate(zip(xs, ys, texts)):
        dx_dir, dy_dir = directions[index % len(directions)]
        if existing_texts is not None:
            if index >= len(existing_texts):
                continue
            artist = existing_texts[index]
            if not artist.get_text():
                continue
            artist.set_position(
                (
                    float(x) + dx_dir * initial_offset_px * x_per_px,
                    float(y) + dy_dir * initial_offset_px * y_per_px,
                )
            )
        else:
            label_text = str(label)
            if not label_text:
                continue
            artist = ax.text(
                float(x) + dx_dir * initial_offset_px * x_per_px,
                float(y) + dy_dir * initial_offset_px * y_per_px,
                label_text,
                ha="center",
                va="center",
                fontsize=fontsize,
                color=color,
                bbox=label_bbox,
                zorder=10,
            )
        artist._graph_hub_leader_target_data = (round(float(x), 12), round(float(y), 12))
        label_artists.append(artist)
        target_x.append(float(x))
        target_y.append(float(y))

    if not label_artists:
        return {"texts": [], "leaders": [], "used_adjust_text": False}

    arrowprops = None
    if leader:
        arrowprops = {"arrowstyle": "-", "color": leader_color, "lw": leader_lw, "shrinkA": 2.0, "shrinkB": 2.0}
    kwargs = {
        "x": list(map(float, xs)),
        "y": list(map(float, ys)),
        "target_x": target_x,
        "target_y": target_y,
        "ax": ax,
        "ensure_inside_axes": True,
        "prevent_crossings": True,
        "min_arrow_len": float(min_leader_distance_px),
        "iter_lim": 80,
    }
    if arrowprops is not None:
        kwargs["arrowprops"] = arrowprops
    if adjust_kwargs:
        kwargs.update(adjust_kwargs)
    adjusted_texts, leader_patches = adjust_text(label_artists, **kwargs)
    for artist in adjusted_texts:
        artist._graph_hub_leader_connected = False
    for patch in leader_patches:
        patch._graph_hub_leader_patch = True
        patch_text = getattr(patch, "patchA", None)
        if patch_text is not None:
            patch_text._graph_hub_leader_connected = True
    return {"texts": adjusted_texts, "leaders": leader_patches, "used_adjust_text": True}


def get_standard_legend_props(style="top_floating"):
    """
    저널(Nature/Science) 규격 Single Column(89mm)에 최적화된 범례 설정을 반환합니다.
    """
    if style == "top_floating":
        return {"fontsize": 7.0, "loc": "lower center", "bbox_to_anchor": (0.5, 1.02), "ncol": 3, "frameon": False}
    return {"fontsize": 7.0, "frameon": False}


def apply_scientific_padding(ax, data_max, padding_ratio=1.6, data_min=None):
    """
    데이터 상단에 어노테이션(라벨 등)을 위한 여유 공간(Headroom)을 확보합니다.
    1.6배 패딩은 다중 피크 라벨 배치를 위한 충분한 공간을 제공합니다.
    data_min이 None이면 현재 축 하한을 유지합니다 (음수 데이터 대응).
    """
    y_bottom = 0 if (data_min is None or data_min >= 0) else data_min * padding_ratio
    y_top = data_max * padding_ratio if data_max >= 0 else data_max / padding_ratio
    ax.set_ylim(y_bottom, y_top)
    return y_top


def add_peak_annotation(
    ax,
    x,
    y_limit,
    label,
    color="black",
    ls="--",
    alpha=0.4,
    fontsize=None,
    level=1,
    x_offset=0,
    **kwargs,
):
    """
    과학 논문용 피크(Peak) 라벨을 추가합니다.
    fontsize가 None인 경우 rcParams['axes.labelsize']를 따릅니다.
    """
    if fontsize is None:
        fontsize = plt.rcParams.get("axes.labelsize", 7.0)
    # level에 따른 세로 위치 조정 — 축 상단 안쪽에 배치
    y_pos = y_limit * max(0.15, 0.88 - (level - 1) * 0.14)

    # 수직 가이드라인
    ax.axvline(x, color=color, ls=ls, alpha=alpha, lw=0.8, zorder=1)

    ha = kwargs.get("ha", "center")
    # 텍스트 라벨 (반투명 배경 박스)
    ax.text(
        x + x_offset,
        y_pos,
        label,
        fontsize=fontsize,
        ha=ha,
        va="center",
        color=color,
        fontweight="bold",
        zorder=10,
        bbox=dict(facecolor="white", alpha=0.9, edgecolor="none", pad=2.0),
    )


def annotate_significance(
    ax,
    x1: float,
    x2: float,
    y: float,
    label: str = "*",
    *,
    h: float | None = None,
    color: str = "black",
) -> None:
    """두 x 위치 사이에 유의성 브래킷(괄호 + *, **, ***)을 추가합니다."""
    if h is None:
        y_lo, y_hi = ax.get_ylim()
        h = (y_hi - y_lo) * 0.02  # 현재 y범위의 2%를 브래킷 높이로 사용
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=0.8, color=color)
    ax.text(
        (x1 + x2) / 2,
        y + h,
        label,
        ha="center",
        va="bottom",
        fontsize=plt.rcParams.get("axes.labelsize", 7.0),
        color=color,
    )


def apply_auto_units(ax, x_col, y_col, project_config):
    """
    Automatically attaches units to axes labels based on project_config.yaml data_contract.
    Does not overwrite existing labels if manually set.
    """
    data_contract = project_config.get("data_contract", {})
    csv_checks = data_contract.get("csv_checks", [])

    # Flatten units from all csv_checks
    units = {}
    for check in csv_checks:
        semantic_checks = check.get("semantic_checks", {})
        for col, rules in semantic_checks.items():
            if isinstance(rules, dict) and "unit" in rules:
                units[col] = rules["unit"]
            elif isinstance(rules, dict) and "unit" in rules.get("range", {}):  # fallback if nested
                units[col] = rules["range"]["unit"]

    # Update X axis if not manually set
    if x_col in units and not ax.get_xlabel():
        ax.set_xlabel(f"{x_col} [{units[x_col]}]")

    # Update Y axis if not manually set
    if y_col in units and not ax.get_ylabel():
        ax.set_ylabel(f"{y_col} [{units[y_col]}]")
