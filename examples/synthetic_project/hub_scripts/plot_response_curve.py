from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from themes.journal_theme import apply_journal_theme, save_journal_fig


def main() -> None:
    data = pd.read_csv("results/data/response_curve.csv")
    apply_journal_theme("nature", profile_name="baseline")

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
    save_journal_fig(fig, output)
    plt.close(fig)


if __name__ == "__main__":
    main()
