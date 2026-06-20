
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

# 모듈 경로 추가 (Graph_making_hub 루트를 추가)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotting.bridge_renderer import draw_zenith_plot
from plotting.utils import add_smart_inset, auto_panel_tag
from themes.journal_theme import apply_journal_theme


def run_demo():
    # 1. 테마 적용 (Nature 규격)
    apply_journal_theme(target_format='nature')

    # 2. 가상 데이터 생성 (밀도가 높은 구간 포함)
    np.random.seed(42)
    x = np.linspace(0, 10, 200)
    y = np.sin(x) + np.random.normal(0, 0.2, 200)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))

    # --- Case 1: Messy Plot (기본) ---
    ax1.scatter(x, y, color='blue', label='Raw Data (Messy)')
    ax1.legend(loc='upper right')
    ax1.set_title("Standard Matplotlib")
    auto_panel_tag(ax1, 'a')

    # --- Case 2: Zenith Plot (지능형) ---
    draw_zenith_plot(ax2, x, y, label='Optimized Data (Zenith)', kind='scatter', palette='Nature Energy')

    # 인셋 추가 (자동 위치 및 스케일링)
    inset = add_smart_inset(ax2, position='lower_left', size=0.35)
    inset.plot(x[:50], y[:50], color='red', lw=0.5)
    inset.set_xticks([])
    inset.set_yticks([])

    ax2.set_title("Graph Visual Zenith")
    auto_panel_tag(ax2, 'b')

    plt.tight_layout()

    # 결과 저장
    output_path = "zenith_demo_comparison.png"
    plt.savefig(output_path, dpi=300)
    print(f"Demo comparison saved to: {output_path}")
    plt.close()

if __name__ == "__main__":
    run_demo()
