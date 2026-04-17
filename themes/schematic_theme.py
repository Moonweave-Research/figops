"""
[Graph_making_hub]/themes/schematic_theme.py
============================================
도식/모식도 전용 테마 엔진 (Schematic/Diagram Theme Engine)

[역할]
- 연구 데이터 그래프가 아닌, 구조도나 작동 원리를 설명하는 '도식' 전용 스타일 제공
- TikZ/LaTeX 특유의 정갈하고 학술적인 미학(Aesthetic) 재현
- 축(Axis) 정보 제거, 전용 화살표 스타일 표준화

[사용법] apply_schematic_theme 는 두 가지 방식 모두 지원한다.

  방식 A — plain call (subprocess 격리 스크립트, 하위 호환):
      apply_schematic_theme(style='tikz')
      # 이후 코드에 영구 적용

  방식 B — context manager (in-process 렌더링, 데이터 플롯 오염 방지):
      with apply_schematic_theme():
          fig, ax = plt.subplots(...)
          ...
      # 블록 종료 시 rcParams 자동 복원
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch


def _build_rc_settings(style: str, font_scale: float) -> dict:
    if style == "tikz":
        return {
            "font.family":         "sans-serif",
            "font.sans-serif":     ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
            "mathtext.fontset":    "custom",
            "mathtext.rm":         "Arial",
            "mathtext.it":         "Arial:italic",
            "mathtext.bf":         "Arial:bold",
            # Remove all axis/grid elements — schematic has no data axes
            "axes.linewidth":      0,
            "axes.grid":           False,
            "xtick.major.size":    0,
            "ytick.major.size":    0,
            "xtick.labelsize":     7.0 * font_scale,
            "ytick.labelsize":     7.0 * font_scale,
            "axes.titlesize":      7.5 * font_scale,
            "axes.titleweight":    "bold",
            # Rendering
            "savefig.dpi":         600,
            "savefig.bbox":        "tight",
            "savefig.transparent": False,
        }
    return {"font.family": "sans-serif"}


class apply_schematic_theme:
    """이중 모드 테마 적용기.

    Plain call — 영구 적용 (subprocess 격리 hub_scripts 하위 호환):
        apply_schematic_theme(style='tikz')

    Context manager — 블록 범위 적용 후 자동 복원 (in-process 렌더링):
        with apply_schematic_theme():
            ...
    """

    def __init__(self, style: str = "tikz", font_scale: float = 1.0):
        self._rc = _build_rc_settings(style, font_scale)
        # 현재 rcParams 상태 저장 (context manager exit 시 복원용)
        self._saved = {k: plt.rcParams[k] for k in self._rc if k in plt.rcParams}
        # 즉시 적용 (plain call 하위 호환)
        plt.rcParams.update(self._rc)

    def __enter__(self):
        # __init__ 에서 이미 적용됨 — 추가 작업 불필요
        return self

    def __exit__(self, *exc):
        # 저장해둔 상태로 복원
        plt.rcParams.update(self._saved)
        return False

def get_schematic_palette(theme='nature_soft'):
    """
    도식에 적합한 부드러운 파스텔톤 팔레트를 반환합니다.
    """
    if theme == 'nature_soft':
        return {
            'blue_active':   '#C6DBEF', # Ideal/Active LCE
            'blue_inactive': '#F0F4F8', # Faded/Dead Zone
            'red_theft':     '#F88379', # Coating/Voltage Theft
            'red_bold':      '#FB6A4A', # Warning/Expansion
            'charcoal':      '#414141', # Electrode
            'gray_dim':      '#7F8C8D'  # Supplemental text
        }
    return {}

def get_arrow_props(type='field'):
    """
    도식 전용 FancyArrowPatch 속성을 반환합니다.
    """
    if type == 'field': # 전계/포스 라인
        return dict(arrowstyle='<|-|>', mutation_scale=6, color='gray', lw=0.6, ls='--', alpha=0.5)
    elif type == 'expansion': # 팽창/변형
        return dict(arrowstyle='simple, head_width=5, head_length=5', color='#FB6A4A', lw=0.5)
    elif type == 'theft': # 전압 도둑/집중
        return dict(arrowstyle='-|>', mutation_scale=6, color='black', lw=0.8)
    return {}
