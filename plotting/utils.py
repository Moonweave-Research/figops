"""
[Graph_making_hub]/plotting/utils.py
===================================
🔧 시각화 유틸리티 함수 (Reusable Visualization Helpers)

[역할 / Role]
- 논문용 그래프 작성 시 반복되는 텍스트 처리 및 레이아웃 최적화 로직 제공
- 샘플 라벨 축약, 범례 위치 최적화 등 "세밀한 한 끗"을 자동화

[주요 함수 / Key Functions]
- compress_sample_label: 지저분한 샘플명을 논문 규격으로 축약
- get_standard_legend_props: 소형 피규어(89mm)에 최적화된 범례 속성 반환
"""

import matplotlib.pyplot as plt
from .smart_layout import find_empty_quadrant

def add_smart_inset(ax, position='upper_right', size=0.3, padding=0.05, label_scale=0.8):
    """
    선언적으로 인셋(Inset)을 추가합니다. 
    메인 축의 폰트 크기보다 작게(기본 0.8배) 자동 조정됩니다.
    """
    # [0, 0, 1, 1] 비율 좌표계에서의 위치 계산
    presets = {
        'upper_right': [1 - size - padding, 1 - size - padding, size, size],
        'upper_left': [padding, 1 - size - padding, size, size],
        'lower_right': [1 - size - padding, padding, size, size],
        'lower_left': [padding, padding, size, size]
    }
    
    rect = presets.get(position, presets['upper_right'])
    inset_ax = ax.inset_axes(rect)
    
    # 폰트 스케일링 설정 (Matplotlib은 수동 폰트 조정이 필요하므로, 이후 테마 적용 시 활용 가능)
    # 여기서는 간단히 축 라벨 크기 조정을 시연
    inset_ax.tick_params(labelsize=plt.rcParams['font.size'] * label_scale)
    
    return inset_ax

def auto_panel_tag(ax, label='a', x_offset=-0.12, y_offset=1.05):
    """
    패널 식별자(a, b, c)를 표준화된 위치(Top-left)에 배치합니다.
    """
    ax.text(x_offset, y_offset, f"{label})", 
            transform=ax.transAxes, 
            fontsize=plt.rcParams['axes.titlesize'] + 1,
            fontweight='bold', 
            va='bottom', ha='right')

def apply_density_alpha(dataset_size, base_alpha=0.6, base_size=10):
    """
    데이터 밀도에 따라 점의 투명도와 크기를 자동으로 조절하여 뭉침을 방지합니다.
    """
    if dataset_size > 1000:
        alpha = base_alpha * 0.4
        size = base_size * 0.5
    elif dataset_size > 100:
        alpha = base_alpha * 0.7
        size = base_size * 0.8
    else:
        alpha = base_alpha
        size = base_size
        
    return alpha, size

def compress_sample_label(label: str) -> str:
    """
    지저분한 샘플 이름을 논문용으로 깔끔하게 축약합니다.
    (예: "Coated Sample_Noa_None_Aligned" -> "Coated, Noa, None, Aln.")
    """
    if not isinstance(label, str):
        return str(label)
    
    replacements = {
        'Coated Sample_': 'Coated, ',
        ' Removed': ' Rem.',
        ' + ': '+',
        '_': ', ',
        'Aligned': 'Aln.',
        'Unaligned': 'Unaln.',
        'None': 'None',
        'None, None': 'None'
    }
    
    compressed = label
    for old, new in replacements.items():
        compressed = compressed.replace(old, new)
    
    # 중복 쉼표 및 공백 정리
    compressed = compressed.replace(', ,', ',').strip(', ')
    return compressed

def get_standard_legend_props(style='top_floating'):
    """
    저널(Nature/Science) 규격 Single Column(89mm)에 최적화된 범례 설정을 반환합니다.
    """
    if style == 'top_floating':
        return {
            'fontsize': 4.5,
            'loc': 'lower center',
            'bbox_to_anchor': (0.5, 1.02),
            'ncol': 2,
            'frameon': False
        }
    return {'fontsize': 5, 'frameon': True}

def apply_scientific_padding(ax, data_max, padding_ratio=1.45):
    """
    데이터 상단에 어노테이션(라벨 등)을 위한 여유 공간(Headroom)을 확보합니다.
    """
    ax.set_ylim(0, data_max * padding_ratio)
    return data_max * padding_ratio

def add_peak_annotation(ax, x, y_limit, label, color='black', ls='--', alpha=0.4, fontsize=7, level=1):
    """
    과학 논문용 피크(Peak) 라벨을 추가합니다. 
    level 인자를 통해 라벨 간 수직 겹침을 방지할 수 있습니다.
    """
    # level에 따른 세로 위치 조정 (더 큰 간격 확보: 0.94, 0.80, 0.66...)
    y_pos = y_limit * (0.94 - (level - 1) * 0.14)
    
    # 수직 가이드라인
    ax.axvline(x, color=color, ls=ls, alpha=alpha, lw=0.8, zorder=1)
    
    # 텍스트 라벨 (가독성을 위해 배경을 더 불투명하게 조정)
    ax.text(x, y_pos, label, 
            fontsize=fontsize, ha="center", va="center",
            color=color, fontweight="bold",
            zorder=10, # 텍스트를 최상단으로
            bbox=dict(facecolor='white', alpha=0.9, edgecolor='none', pad=0.8))
