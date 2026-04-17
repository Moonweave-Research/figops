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

from journal_theme import apply_journal_theme, set_figure_size, SINGLE_COLUMN, WT_COLORS
from common_plots import draw_pvalue_bracket

# 전역 테마 적용
apply_journal_theme()

# ── [경로 설정] ──────────────────────────────────────────
PROJECT_ROOT = os.environ.get('PROJECT_ROOT', os.getcwd())
data_path = os.path.join(PROJECT_ROOT, "results/data/Fig5_resistivity_summary.csv")


def run_test():
    df = pd.read_csv(data_path)

    # ── Figure 생성 - Nature Single Column 규격 ────────────────────────
    w, h = set_figure_size(SINGLE_COLUMN, ratio=0.8)
    fig, ax = plt.subplots(figsize=(w, h), dpi=600)

    # 1. 데이터 시각화 (Bar + Points)
    wt_list = sorted(df['wt'].unique())
    colors = [WT_COLORS.get(wt, "#7F8C8D") for wt in wt_list]

    means = df.groupby('wt')['Increase Rate'].mean()
    stds = df.groupby('wt')['Increase Rate'].std()

    ax.bar(range(len(wt_list)), means, color=colors, edgecolor='black', lw=0.5, alpha=0.8)

    # Individual Data Points (Jitter)
    for i, wt in enumerate(wt_list):
        y_vals = df[df['wt'] == wt]['Increase Rate']
        x_jitter = np.random.normal(i, 0.05, size=len(y_vals))
        ax.scatter(x_jitter, y_vals, s=5, c='white', edgecolors='black', lw=0.3, zorder=3)

    # 2. 유의성 마커 (Lean Helper)
    draw_pvalue_bracket(ax, x1=0, x2=4, y=250, text='p < 0.001 (***)', lw=0.6, fontsize=6)

    # 3. 축 설정
    ax.set_ylabel(r"$\rho_{final} / \rho_{init}$ (Increase Rate)")
    ax.set_xlabel("Sulfur Content (wt%)")
    ax.set_yscale('log')
    ax.set_ylim(1, 1000)

    ax.set_xticks(range(len(wt_list)))
    ax.set_xticklabels(wt_list)

    # 4. 저장
    output_path = os.path.join(PROJECT_ROOT, "results/figures/Evolution_Test_Fig1_Lean.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    fig.savefig(output_path, bbox_inches='tight')
    print(f"Success: {output_path}")


if __name__ == "__main__":
    run_test()
