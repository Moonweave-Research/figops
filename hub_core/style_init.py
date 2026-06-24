"""
hub_core/style_init.py
======================
FigOps 스타일 초기화 헬퍼.

hub_scripts/*.py 상단에서 한 줄로 호출하여
project_config.yaml → process_runner → env var → apply_journal_theme
파이프라인을 완성합니다.

사용법:
    from hub_core.style_init import apply_hub_style
    fmt, scale = apply_hub_style()

또는 반환값이 필요 없을 때:
    from hub_core.style_init import apply_hub_style
    apply_hub_style()

process_runner.py가 주입하는 env var:
    THEME_FORMAT  : target_format  (예: 'nature', 'ppt')
    THEME_SCALE   : font_scale     (예: '1.0', '1.2')
    THEME_PROFILE : profile_name   (예: 'baseline')
"""

from __future__ import annotations

import os
import sys


def _ensure_hub_in_path() -> None:
    """RESEARCH_HUB_PATH 가 sys.path 에 포함되도록 보장합니다."""
    hub_path = os.environ.get("RESEARCH_HUB_PATH")
    if not hub_path:
        # 폴백: style_init.py 기준으로 상위 디렉토리 추정
        hub_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if hub_path not in sys.path:
        sys.path.insert(0, hub_path)


def apply_hub_style() -> tuple[str, float]:
    """
    project_config.yaml 의 visual_style 설정을 env var 로 받아
    apply_journal_theme() 를 호출합니다.

    Returns
    -------
    tuple[str, float]
        (target_format, font_scale) — 스크립트에서 참조가 필요할 때 사용.
    """
    _ensure_hub_in_path()

    target_format = os.environ.get("THEME_FORMAT", "nature").lower()
    font_scale = float(os.environ.get("THEME_SCALE", "1.0"))
    profile_name = os.environ.get("THEME_PROFILE", "baseline")

    try:
        from themes.journal_theme import apply_journal_theme  # noqa: PLC0415
        apply_journal_theme(
            target_format=target_format,
            font_scale=font_scale,
            profile_name=profile_name,
        )
    except ImportError:
        pass  # Hub 경로 미설정 환경에서는 조용히 건너뜀

    return target_format, font_scale
