from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    data = pd.read_csv("results/data/polymer_material_properties.csv")
    plt.rcParams.update(
        {
            "font.size": 7,
            "axes.labelsize": 7,
            "axes.titlesize": 8,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "figure.dpi": 300,
        }
    )

    fig, ax1 = plt.subplots(figsize=(3.35, 2.2))
    ax1.plot(
        data["time_s"],
        data["corrected_signal_au"],
        marker="o",
        linewidth=1.2,
        markersize=3.5,
        color="#2f6f9f",
        label="Corrected signal",
    )
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Corrected signal (a.u.)")
    ax1.spines["top"].set_visible(False)

    ax2 = ax1.twinx()
    ax2.plot(
        data["time_s"],
        data["resistivity_ohm_cm"],
        marker="s",
        linewidth=1.1,
        markersize=3.0,
        color="#b44d35",
        label="Resistivity",
    )
    ax2.set_ylabel("Resistivity (Ohm cm)")
    ax2.spines["top"].set_visible(False)

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, frameon=False, loc="upper left")

    output = Path("results/figures/polymer_domain_helper.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
