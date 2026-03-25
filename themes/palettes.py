"""
[Graph_making_hub]/themes/palettes.py
=====================================
🎨 연구용 팔레트 컬렉션 (Publication-Quality Color Palettes)

[역할 / Role]
- 모든 프로젝트에서 일관된 색상 사용을 보장하는 "색상 단일 진실원"
- Nature / Science 투고에 적합한 팔레트만 엄선
- Python & R 양측에서 참조 가능하도록 순수 데이터로만 구성 (import 불필요)

[키워드 / Keywords]
  RESEARCH_COLOR_PALETTES  ← 22종 팔레트 dict (이름 → hex color list)
  RESEARCH_PALETTE_GROUPS  ← 그룹별 팔레트 분류 (Pastel / Publication / Sequential / Accessibility)
  JOURNAL_PRESET_SPECS     ← 저널별 그림 크기 & 폰트 규격 (Nature, Science, ACS, RSC, Elsevier)
  get_palette(name)        ← 이름으로 팔레트 가져오기
  list_palettes()          ← 그룹별 팔레트 목록 출력

[사용법 / Usage]
  from palettes import RESEARCH_COLOR_PALETTES, get_palette, JOURNAL_PRESET_SPECS

  # 팔레트 직접 사용
  colors = RESEARCH_COLOR_PALETTES['Okabe-Ito']   # 색맹 안전 팔레트

  # 헬퍼 함수 사용
  colors = get_palette('Nature Journal')           # 없으면 기본 팔레트 반환

  # 저널 규격 확인
  w, h, title_pt, label_pt, tick_pt, lw, dpi = JOURNAL_PRESET_SPECS['Nature (89mm)']

[팔레트 그룹 / Palette Groups]
  Pastel       : Pastel Neutral, Pastel Soft, Pastel Cool, Pastel Warm, Nature Pastel, Pastel Contrast
  Publication  : Muted Professional, Tableau 10, Nature Journal, Nature Earth, Deep/Muted (Seaborn), Tol Bright
  Sequential   : Viridis 8, Cividis 8, Magma 8, Ocean, Forest, Sunset
  Accessibility: Colorblind Safe, Okabe-Ito, Set2/Set3 (Seaborn)

[출처 / Source]
  Migrated from: Coriding Hub/Graph 코드/Codes/graph_shared.py (RESEARCH_COLOR_PALETTES 섹션)
  Migration date: 2026-03-02
"""

import os

import yaml

# ── YAML에서 데이터 로드 (Single Source of Truth) ───────────────────────────
_yaml_path = os.path.join(os.path.dirname(__file__), "palettes.yaml")

try:
    with open(_yaml_path, "r", encoding="utf-8") as _f:
        _data = yaml.safe_load(_f)
except FileNotFoundError:
    _data = {}
    print(f"Warning: {_yaml_path} not found. Fallback to empty palettes.")

# ── 글로벌 변수 매핑 ──────────────────────────────────────────────────────
RESEARCH_COLOR_PALETTES = _data.get("RESEARCH_COLOR_PALETTES", {})

# WT_COLORS 키를 정수로 매핑
_wt_colors_raw = _data.get("WT_COLORS", {})
WT_COLORS = {int(k) if str(k).isdigit() else k: v for k, v in _wt_colors_raw.items()}

# RESEARCH_PALETTE_GROUPS 튜플화
_raw_groups = _data.get("RESEARCH_PALETTE_GROUPS", [])
RESEARCH_PALETTE_GROUPS = [(g[0], g[1]) for g in _raw_groups]

# JOURNAL_PRESET_SPECS 값 튜플화
_raw_specs = _data.get("JOURNAL_PRESET_SPECS", {})
JOURNAL_PRESET_SPECS = {k: tuple(v) for k, v in _raw_specs.items()}

JOURNAL_PRESET_ORDER = tuple(_data.get("JOURNAL_PRESET_ORDER", []))


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────
def get_palette(name: str, default: str = "Muted Professional") -> list:
    """이름으로 팔레트를 가져온다. 없으면 default 팔레트를 반환.

    Parameters
    ----------
    name : str
        RESEARCH_COLOR_PALETTES의 키
    default : str
        존재하지 않는 이름일 때 반환할 팔레트 이름

    Returns
    -------
    list of str
        hex color 리스트 (mutable copy)

    Example
    -------
    colors = get_palette('Okabe-Ito')
    ax.set_prop_cycle(color=colors)
    """
    palette = RESEARCH_COLOR_PALETTES.get(name) or RESEARCH_COLOR_PALETTES.get(default, [])
    result = list(palette)
    if not result:
        result = ["#4878D0", "#EE854A", "#6ACC64", "#D65F5F"]
    return result


def list_palettes(verbose: bool = False) -> None:
    """그룹별 팔레트 목록을 출력.

    Parameters
    ----------
    verbose : bool
        True면 hex 색상 코드까지 출력
    """
    for group, names in RESEARCH_PALETTE_GROUPS:
        print(f"\n[{group}]")
        for name in names:
            colors = RESEARCH_COLOR_PALETTES.get(name, [])
            if verbose:
                print(f"  {name:25s} : {colors}")
            else:
                print(f"  {name}")
