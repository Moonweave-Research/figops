from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    data = pd.read_csv("results/data/response_curve.csv")
    plt.rcParams.update(
        {
            "font.size": 7,
            "axes.labelsize": 7,
            "axes.titlesize": 8,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "legend.fontsize": 6,
            "figure.dpi": 300,
        }
    )

    fig, ax = plt.subplots(figsize=(3.35, 2.2))
    ax.plot(data["time_s"], data["response_au"], marker="o", linewidth=1.2, markersize=3.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Response (a.u.)")
    ax.set_title("Synthetic response")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    output = Path("results/figures/FigSynthetic_Response.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
