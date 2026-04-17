"""
Physics-aware colormap resolution.

Maps physical quantity types to perceptually appropriate colormaps.
Diverging colormaps (e.g., RdBu_r) for quantities with meaningful zero crossings,
sequential colormaps for positive-definite quantities.
"""

from __future__ import annotations

PHYSICS_COLORMAP_MAP: dict[str, str] = {
    # Diverging (meaningful zero or bipolar)
    "temperature": "coolwarm",
    "electric_field": "RdBu_r",
    "voltage": "RdBu_r",
    "potential": "RdBu_r",
    "charge_density": "RdBu_r",
    # Sequential (positive-definite)
    "strain": "viridis",
    "displacement": "viridis",
    "stress": "magma",
    "conductivity": "plasma",
    "modulus": "inferno",
    "frequency": "cividis",
    "viscosity": "cividis",
    "permittivity": "plasma",
    "dielectric": "plasma",
}


def resolve_colormap(physics_type: str | None, fallback: str = "viridis") -> str:
    """Return the best colormap for a given physics quantity type.

    Falls back to *fallback* when *physics_type* is empty or unknown.
    """
    if not physics_type:
        return fallback
    return PHYSICS_COLORMAP_MAP.get(physics_type.lower().strip(), fallback)
