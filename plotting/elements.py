"""
[Graph_making_hub]/plotting/elements.py
======================================
🚀 Publication-Ready Schematic Elements Library (v4.1)

[역할 / Role]
- 학술 논문 도식에 사용되는 표준 물리/화학/측정 요소를 그리는 함수 제공
- AI가 파라미터를 통해 완벽하게 제어할 수 있도록 상세한 Docstring과 타입 명세 포함
- 모든 시각적 요소는 Matplotlib 기반의 벡터 그래픽으로 생성됨

[업데이트 내역 / Changelog]
- v4.0: draw_cantilever_beam 추가
- v4.1: draw_electrode_array, draw_polymer_network, draw_trap_site 추가
"""

from typing import List, Optional, Tuple

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# --- 1. Materials & Structures ---


def draw_cantilever_beam(
    ax,
    pos: Tuple[float, float, float] = (0, 0, 0),
    length: float = 5.0,
    width: float = 1.0,
    thickness: float = 0.3,
    color: str = "#4DD0E1",
    edge_color: str = "black",
    alpha: float = 0.6,
) -> Poly3DCollection:
    """
    Draws a 3D cantilever beam at a given position.

    Args:
        ax: Matplotlib 3D axis.
        pos: (x, y, z) start position (fixed end).
        length: Beam length along X-axis.
        width: Beam width along Y-axis.
        thickness: Beam thickness along Z-axis.
    """
    x0, y0, z0 = pos
    L, W, T = length, width, thickness

    v = np.array(
        [
            [x0, y0, z0],
            [x0 + L, y0, z0],
            [x0 + L, y0 + W, z0],
            [x0, y0 + W, z0],
            [x0, y0, z0 + T],
            [x0 + L, y0, z0 + T],
            [x0 + L, y0 + W, z0 + T],
            [x0, y0 + W, z0 + T],
        ]
    )

    faces = [
        [v[0], v[1], v[5], v[4]],
        [v[1], v[2], v[6], v[5]],
        [v[2], v[3], v[7], v[6]],
        [v[3], v[0], v[4], v[7]],
        [v[0], v[1], v[2], v[3]],
        [v[4], v[5], v[6], v[7]],
    ]

    beam = Poly3DCollection(faces, facecolors=color, linewidths=1.2, edgecolors=edge_color, alpha=alpha)
    ax.add_collection3d(beam)
    return beam


def draw_electrode_array(
    ax,
    pos: Tuple[float, float] = (0, 0),
    width: float = 5.0,
    height: float = 3.0,
    finger_count: int = 5,
    finger_width: float = 0.2,
    finger_gap: float = 0.2,
    orientation: str = "horizontal",
    color_pos: str = "#D32F2F",
    color_neg: str = "#1976D2",
    alpha: float = 0.8,
) -> List[patches.Rectangle]:
    """
    Draws a 2D Interdigitated Electrode (IDE) array.

    Args:
        ax: Matplotlib 2D axis.
        pos: (x, y) bottom-left start position.
        width: Total width of the IDE area.
        height: Total height of the IDE area.
        finger_count: Number of fingers PER electrode (total fingers = 2 * count).
        finger_width: Thickness of each finger.
        finger_gap: Gap between adjacent fingers.
        orientation: 'horizontal' (fingers point along X) or 'vertical' (fingers point along Y).
    """
    elements = []
    x0, y0 = pos

    # Calculate finger length (reserve space for bus bars)
    bus_bar_width = 0.3
    f_length = (width - bus_bar_width * 2) if orientation == "horizontal" else (height - bus_bar_width * 2)

    for i in range(finger_count):
        # Position calculation
        offset = i * (finger_width + finger_gap) * 2

        if orientation == "horizontal":
            # Positive finger (Left to Right)
            rect_pos = patches.Rectangle(
                (x0, y0 + offset),
                f_length + bus_bar_width,
                finger_width,
                color=color_pos,
                alpha=alpha,
                ec="black",
                lw=0.5,
            )
            # Negative finger (Right to Left)
            rect_neg = patches.Rectangle(
                (x0 + width - (f_length + bus_bar_width), y0 + offset + finger_width + finger_gap),
                f_length + bus_bar_width,
                finger_width,
                color=color_neg,
                alpha=alpha,
                ec="black",
                lw=0.5,
            )
        else:  # vertical
            rect_pos = patches.Rectangle(
                (x0 + offset, y0),
                finger_width,
                f_length + bus_bar_width,
                color=color_pos,
                alpha=alpha,
                ec="black",
                lw=0.5,
            )
            rect_neg = patches.Rectangle(
                (x0 + offset + finger_width + finger_gap, y0 + height - (f_length + bus_bar_width)),
                finger_width,
                f_length + bus_bar_width,
                color=color_neg,
                alpha=alpha,
                ec="black",
                lw=0.5,
            )

        ax.add_patch(rect_pos)
        ax.add_patch(rect_neg)
        elements.extend([rect_pos, rect_neg])

    return elements


# --- 2. Polymer Physics & Dynamics ---


def draw_polymer_network(
    ax,
    area: Tuple[float, float, float, float] = (0, 10, 0, 6),
    num_chains: int = 8,
    nodes_per_chain: int = 10,
    wiggle: float = 0.3,
    color: str = "#795548",
    alpha: float = 0.4,
    lw: float = 1.5,
    seed: int = 0,
) -> List[plt.Line2D]:
    """
    Draws a randomized polymer network structure.

    Args:
        ax: Matplotlib axis.
        area: (xmin, xmax, ymin, ymax) drawing bounds.
        num_chains: Number of polymer chains to generate.
        wiggle: Randomness factor for chain paths.
        seed: RNG seed; a fixed default keeps the figure byte-reproducible.
    """
    xmin, xmax, ymin, ymax = area
    chains = []
    rng = np.random.default_rng(seed)

    for _ in range(num_chains):
        # Start at left, end at right (approx)
        x = np.linspace(xmin, xmax, nodes_per_chain)
        y = np.linspace(ymin, ymax, nodes_per_chain)
        rng.shuffle(y)  # Randomize vertical path

        # Add 'wiggle' using sine waves + noise
        y += np.sin(x) * wiggle + rng.normal(0, wiggle, nodes_per_chain)

        (line,) = ax.plot(x, y, color=color, alpha=alpha, lw=lw, solid_capstyle="round")
        chains.append(line)

    return chains


def draw_trap_site(
    ax,
    pos: Tuple[float, float],
    radius: float = 0.15,
    color: str = "#FFEB3B",
    label: Optional[str] = "Trap",
    glow: bool = True,
):
    """
    Draws a specific charge trapping site with an optional glow effect.
    """
    x, y = pos
    if glow:
        for r in [radius * 2, radius * 1.5, radius]:
            ax.add_patch(patches.Circle((x, y), r, color=color, alpha=0.2 if r > radius else 1.0, zorder=10))
    else:
        ax.add_patch(patches.Circle((x, y), radius, color=color, ec="black", lw=1, zorder=10))

    if label:
        ax.text(x, y + radius * 1.5, label, fontsize=8, ha="center", fontweight="bold", zorder=11)


# --- 3. Narrative & Mechanism Elements ---


def draw_curved_arrow(
    ax,
    start: Tuple[float, float],
    end: Tuple[float, float],
    curvature: float = 0.3,
    color: str = "#E74C3C",
    lw: float = 2.0,
    arrow_style: str = "->",
    mutation_scale: float = 15,
    alpha: float = 1.0,
    zorder: int = 20,
) -> patches.FancyArrowPatch:
    """Show motion, deformation direction, or ion transport path."""
    arrow = patches.FancyArrowPatch(
        posA=start,
        posB=end,
        connectionstyle=f"arc3,rad={curvature}",
        arrowstyle=arrow_style,
        color=color,
        linewidth=lw,
        mutation_scale=mutation_scale,
        alpha=alpha,
        zorder=zorder,
    )
    ax.add_patch(arrow)
    return arrow


def draw_field_lines(
    ax,
    origin: Tuple[float, float],
    direction: Tuple[float, float],
    num_lines: int = 5,
    spread: float = 1.0,
    length: float = 2.0,
    color: str = "#3498DB",
    lw: float = 1.0,
    linestyle: str = "--",
    alpha: float = 0.7,
    zorder: int = 15,
) -> List:
    """Electric field, stress field, or force field visualization."""
    dx, dy = direction
    norm = np.hypot(dx, dy)
    if norm == 0:
        return []
    ux, uy = dx / norm, dy / norm
    # Perpendicular unit vector (90-degree rotation)
    px, py = -uy, ux

    ox, oy = origin
    artists = []
    for i in range(num_lines):
        t = (i / (num_lines - 1) - 0.5) * spread if num_lines > 1 else 0.0
        sx = ox + px * t
        sy = oy + py * t
        ex = sx + ux * length
        ey = sy + uy * length
        ann = ax.annotate(
            "",
            xy=(ex, ey),
            xytext=(sx, sy),
            arrowprops=dict(
                arrowstyle="->",
                color=color,
                lw=lw,
                ls=linestyle,
                alpha=alpha,
            ),
            zorder=zorder,
        )
        artists.append(ann)
    return artists


def draw_gradient_fill(
    ax,
    bounds: Tuple[float, float, float, float],
    color_start: str = "#3498DB",
    color_end: str = "#E74C3C",
    direction: str = "horizontal",
    alpha: float = 0.5,
    zorder: int = 5,
):
    """Concentration gradient, stress distribution, or temperature field."""
    import matplotlib.colors as mcolors

    cmap = mcolors.LinearSegmentedColormap.from_list("grad", [color_start, color_end])
    x0, x1, y0, y1 = bounds

    if direction == "horizontal":
        data = np.linspace(0, 1, 256).reshape(1, 256)
    else:
        data = np.linspace(0, 1, 256).reshape(256, 1)

    img = ax.imshow(
        data,
        aspect="auto",
        cmap=cmap,
        extent=[x0, x1, y0, y1],
        alpha=alpha,
        origin="lower",
        zorder=zorder,
    )
    return img


def draw_zoom_circle(
    ax,
    center: Tuple[float, float],
    radius: float,
    zoom_center: Tuple[float, float],
    zoom_radius: float,
    color: str = "#2C3E50",
    lw: float = 1.5,
    fill: bool = False,
    alpha: float = 1.0,
    zorder: int = 25,
) -> Tuple:
    """Magnification inset showing microstructure detail."""
    src_circle = patches.Circle(
        center,
        radius,
        fill=fill,
        edgecolor=color,
        linewidth=lw,
        alpha=alpha,
        zorder=zorder,
    )
    zoom_circle = patches.Circle(
        zoom_center,
        zoom_radius,
        fill=fill,
        edgecolor=color,
        linewidth=lw,
        alpha=alpha,
        zorder=zorder,
    )
    ax.add_patch(src_circle)
    ax.add_patch(zoom_circle)

    cx, cy = center
    zx, zy = zoom_center
    (line1,) = ax.plot(
        [cx, zx],
        [cy + radius, zy + zoom_radius],
        color=color,
        lw=lw,
        alpha=alpha,
        zorder=zorder,
    )
    (line2,) = ax.plot(
        [cx, zx],
        [cy - radius, zy - zoom_radius],
        color=color,
        lw=lw,
        alpha=alpha,
        zorder=zorder,
    )
    return (src_circle, zoom_circle, line1, line2)


def draw_charge_hop(
    ax,
    positions: List[Tuple[float, float]],
    site_radius: float = 0.1,
    site_color: str = "#F39C12",
    path_color: str = "#E74C3C",
    lw: float = 1.5,
    alpha: float = 0.8,
    zorder: int = 20,
) -> Tuple[List[patches.Circle], List[patches.FancyArrowPatch]]:
    """Charge transport path showing hopping between sites."""
    site_artists: List[patches.Circle] = []
    arrow_artists: List[patches.FancyArrowPatch] = []

    for pos in positions:
        circle = patches.Circle(
            pos,
            site_radius,
            color=site_color,
            alpha=alpha,
            zorder=zorder,
        )
        ax.add_patch(circle)
        site_artists.append(circle)

    for i in range(len(positions) - 1):
        arrow = patches.FancyArrowPatch(
            posA=positions[i],
            posB=positions[i + 1],
            connectionstyle="arc3,rad=0.15",
            arrowstyle="->",
            color=path_color,
            linewidth=lw,
            alpha=alpha,
            zorder=zorder,
        )
        ax.add_patch(arrow)
        arrow_artists.append(arrow)

    return (site_artists, arrow_artists)
