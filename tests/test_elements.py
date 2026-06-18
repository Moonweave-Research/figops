"""Tests for schematic element helpers — focus on render reproducibility."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from plotting.elements import draw_polymer_network


def _ydata(ax) -> list[tuple]:
    return [tuple(line.get_ydata()) for line in ax.lines]


def test_draw_polymer_network_is_reproducible_by_default():
    """Two default-seed renders must be byte-identical (exact-hash regression relies on it)."""
    fig1, ax1 = plt.subplots()
    draw_polymer_network(ax1)
    first = _ydata(ax1)
    plt.close(fig1)

    fig2, ax2 = plt.subplots()
    draw_polymer_network(ax2)
    second = _ydata(ax2)
    plt.close(fig2)

    assert first == second


def test_draw_polymer_network_seed_changes_layout():
    fig1, ax1 = plt.subplots()
    draw_polymer_network(ax1, seed=1)
    first = _ydata(ax1)
    plt.close(fig1)

    fig2, ax2 = plt.subplots()
    draw_polymer_network(ax2, seed=2)
    second = _ydata(ax2)
    plt.close(fig2)

    assert first != second
