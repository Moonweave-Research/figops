"""Tests for physics-aware colormap resolution."""

from __future__ import annotations

from themes.physics_colormap import PHYSICS_COLORMAP_MAP, resolve_colormap


class TestResolveColormap:
    def test_known_physics_types(self):
        for physics_type, expected_cmap in PHYSICS_COLORMAP_MAP.items():
            assert resolve_colormap(physics_type) == expected_cmap

    def test_case_insensitive(self):
        assert resolve_colormap("Temperature") == "coolwarm"
        assert resolve_colormap("ELECTRIC_FIELD") == "RdBu_r"

    def test_strips_whitespace(self):
        assert resolve_colormap("  strain  ") == "viridis"

    def test_unknown_returns_fallback(self):
        assert resolve_colormap("unknown_quantity") == "viridis"

    def test_custom_fallback(self):
        assert resolve_colormap("unknown_quantity", fallback="plasma") == "plasma"

    def test_empty_string_returns_fallback(self):
        assert resolve_colormap("") == "viridis"

    def test_none_returns_fallback(self):
        assert resolve_colormap(None) == "viridis"
