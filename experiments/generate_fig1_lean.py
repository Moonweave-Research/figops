import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# ── [Lean Hub 연동] ──────────────────────────────────────────────
HUB_ROOT = os.environ.get('RESEARCH_HUB_PATH')
if not HUB_ROOT:
    raise EnvironmentError("CRITICAL: 'RESEARCH_HUB_PATH' environment variable is not set. Please set it to the [Graph_making_hub] absolute path.")
HUB_ROOT = os.path.abspath(HUB_ROOT)
sys.path.insert(0, os.path.join(HUB_ROOT, "themes"))
sys.path.insert(0, os.path.join(HUB_ROOT, "plotting"))

from journal_theme import apply_journal_theme, set_figure_size, DOUBLE_COLUMN, WT_COLORS
from common_plots import draw_pvalue_bracket

# 1. 전역 테마 적용 (Sulfur Project Standard)
apply_journal_theme()

# ── [설정 및 경로] ───────────────────────────────────────────────
PROJECT_ROOT = os.environ.get('PROJECT_ROOT', os.getcwd())
data_path = os.path.join(PROJECT_ROOT, "results/data/Fig5_resistivity_summary.csv")
output_dir = os.path.join(PROJECT_ROOT, "results/figures/test_unification")
os.makedirs(output_dir, exist_ok=True)

# ── [Figure 생성 - Fig 1: Resistivity Summary] ────────────────────
def generate_fig1():
    try:
        df = pd.read_csv(data_path)
        wt_list = sorted(df['wt'].unique())
        
        # 183mm x 75mm (안정적인 3패널 비율)
        w, h = set_figure_size(DOUBLE_COLUMN, 75)
        fig, axes = plt.subplots(1, 3, figsize=(w, h), dpi=600)
        
        metrics = [
            ('Initial Resistivity', axes[0], 'Initial Resistivity', r"$\rho_{init}$ ($\Omega \cdot cm$)", (1e13, 2e16)),
            ('Final Resistivity', axes[1], 'Final Resistivity', r"$\rho_{final}$ ($\Omega \cdot cm$)", (1e14, 3e17)),
            ('Increase Rate', axes[2], 'Resistivity Increase Rate', r"$\rho_{final} / \rho_{init}$", (1, 1000))
        ]
        
        for metric, ax, title, ylabel, ylim in metrics:
            means, err_low, err_high = [], [], []
            
            # Log-Statistics 기반 에러바 계산
            for wt in wt_list:
                vals = df.loc[df['wt'] == wt, metric].values
                log_vals = np.log10(vals)
                m_log, s_log = np.mean(log_vals), np.std(log_vals, ddof=1)
                
                center = 10**m_log
                means.append(center)
                err_low.append(center - 10**(m_log - s_log))
                err_high.append(10**(m_log + s_log) - center)
            
            # 1. 배경 추세선
            ax.plot(range(len(wt_list)), means, ls='--', c='gray', lw=0.5, alpha=0.3, zorder=0)
            
            # 2. 메인 포인트 & 지터
            yerr = np.vstack([err_low, err_high])
            for i, wt in enumerate(wt_list):
                c = WT_COLORS.get(wt, "grey")
                # Errorbar
                ax.errorbar(i, means[i], yerr=yerr[:, i:i+1], fmt='o', color=c, 
                            ecolor='black', capsize=2, elinewidth=0.8, ms=5, 
                            mec='black', mew=0.5, zorder=4)
                # Jitter Points
                raw_y = df.loc[df['wt'] == wt, metric].values
                xj = np.random.normal(i, 0.06, size=len(raw_y))
                ax.scatter(xj, raw_y, s=6, fc='white', ec=c, lw=0.4, alpha=0.5, zorder=3)
            
            # 3. 표준 스타일 적용
            ax.set_title(title, pad=5)
            ax.set_ylabel(ylabel)
            ax.set_xlabel("Sulfur Content (wt%)")
            ax.set_yscale('log')
            ax.set_ylim(ylim)
            ax.set_xticks(range(len(wt_list)))
            ax.set_xticklabels([str(int(w)) for w in wt_list])
            
        # 4. 유의성 브라켓 (Lean Helper)
        draw_pvalue_bracket(axes[2], x1=0, x2=4, y=450, text='p < 0.001 (***)', lw=0.6)
        
        plt.tight_layout(pad=1.2)
        save_path = os.path.join(output_dir, "Fig1_Lean_Hub_Test.png")
        fig.savefig(save_path, bbox_inches='tight')
        print(f"✅ Figure 1 successfully generated at: {save_path}")
        
    except Exception as e:
        print(f"❌ Error generating Fig 1: {e}")

if __name__ == "__main__":
    generate_fig1()
