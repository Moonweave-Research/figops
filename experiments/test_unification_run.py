import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ── [Lean Hub 연동] ──────────────────────────────────────────────
HUB_PATH = os.environ.get('RESEARCH_HUB_PATH')
if not HUB_PATH:
    raise EnvironmentError("CRITICAL: 'RESEARCH_HUB_PATH' environment variable is not set. Please set it to the [Graph_making_hub] absolute path.")
HUB_PATH = os.path.abspath(HUB_PATH)
sys.path.insert(0, os.path.join(HUB_PATH, "themes"))
sys.path.insert(0, os.path.join(HUB_PATH, "plotting"))

from journal_theme import apply_journal_theme, set_figure_size, DOUBLE_COLUMN, WT_COLORS
from common_plots import draw_pvalue_bracket

# 전역 테마 적용
apply_journal_theme()

# ── [경로 설정] ──────────────────────────────────────────
PROJECT_ROOT = os.environ.get('PROJECT_ROOT', os.getcwd())
data_path = os.path.join(PROJECT_ROOT, "results/data/Fig5_resistivity_summary.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "results/figures/test_unification")


def run_test():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df_all = pd.read_csv(data_path)
    wt_list = sorted(df_all['wt'].unique())

    # ── Figure 생성 (183mm x 75mm, 3-panel) ──────────────────
    w, h = set_figure_size(DOUBLE_COLUMN, 75)
    fig, axes = plt.subplots(1, 3, figsize=(w, h), dpi=600)

    metrics = [
        ('Initial Resistivity', axes[0], 'Initial Resistivity (5-10 s)',
         r"$\rho_{init}$ ($\Omega \cdot cm$)", (1e13, 2e16)),
        ('Final Resistivity', axes[1], 'Final Resistivity (900-1000 s)',
         r"$\rho_{final}$ ($\Omega \cdot cm$)", (1e14, 3e17)),
        ('Increase Rate', axes[2], 'Resistivity Increase Rate',
         r"$\rho_{final} / \rho_{init}$", (1, 1000))
    ]

    for metric, ax, title, ylabel, ylim in metrics:
        means, err_lower, err_upper = [], [], []
        for wt in wt_list:
            vals = df_all.loc[df_all['wt'] == wt, metric].values
            log_vals = np.log10(vals)
            mean_log, sd_log = np.mean(log_vals), np.std(log_vals, ddof=1)
            y_center = 10**mean_log
            means.append(y_center)
            err_lower.append(y_center - 10**(mean_log - sd_log))
            err_upper.append(10**(mean_log + sd_log) - y_center)

        means = np.array(means)
        yerr = np.vstack([err_lower, err_upper])
        ax.plot(range(len(wt_list)), means, linestyle='--', color='gray',
                alpha=0.3, linewidth=0.8, zorder=0)

        for i, wt in enumerate(wt_list):
            color = WT_COLORS.get(int(wt), "grey")
            ax.errorbar(i, means[i], yerr=yerr[:, i:i+1], fmt='o', color=color,
                        ecolor='black', capsize=2, elinewidth=0.8, markersize=6,
                        markeredgecolor='black', markeredgewidth=0.6, alpha=0.9, zorder=4)
            raw_y = df_all.loc[df_all['wt'] == wt, metric].values
            ax.scatter(np.random.normal(i, 0.08, size=len(raw_y)), raw_y, s=8,
                       facecolor='white', edgecolors=color, linewidths=0.5, alpha=0.6, zorder=3)

        ax.set_title(title, pad=5)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Sulfur Content (wt%)")
        ax.set_yscale('log')
        ax.set_ylim(ylim)
        ax.set_xticks(range(len(wt_list)))
        ax.set_xticklabels([f"{int(w)}" for w in wt_list])

    # 유의성 브라켓 (Lean Helper)
    draw_pvalue_bracket(axes[2], x1=0, x2=4, y=450, text='p < 0.001 (***)', lw=0.6)

    plt.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, "Fig1_Unification_Test.png")
    fig.savefig(save_path, bbox_inches='tight', dpi=300)
    print(f"Success: {save_path}")


if __name__ == "__main__":
    run_test()
