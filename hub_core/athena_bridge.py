import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypedDict

import matplotlib.pyplot as plt

from .logging import get_logger

logger = get_logger(__name__)


class RenderManifest(TypedDict, total=False):
    artifact_path: str
    artifact_format: str
    width_mm: float
    height_mm: float
    dpi: int
    layers: int
    view_mode: str
    context: str
    font_strategy: str
    source: str
    timestamp: str


class AthenaBridge:
    """
    [Singleton] Athena-Hub Bridge V2
    아테나 시각화 엔진을 안전하게 로드하고, 허브의 YAML 스펙을 아테나의 고지능 객체로 정밀 매핑합니다.
    """
    _instance = None
    _engine = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AthenaBridge, cls).__new__(cls)
        return cls._instance

    def _find_athena_root(self) -> Optional[str]:
        """환경 변수 및 워크스페이스 구조를 기반으로 아테나 엔진의 루트 경로를 탐색합니다."""
        athena_path = os.environ.get("ATHENA_PATH")
        if not athena_path:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            athena_path = os.path.abspath(os.path.join(current_dir, "..", "..", "[Athena]"))

        if os.path.exists(athena_path):
            return athena_path
        return None

    def load_engine(self) -> bool:
        """아테나 모듈을 동적으로 임포트하고 캐싱합니다."""
        if self._engine:
            return True

        athena_root = self._find_athena_root()
        if not athena_root:
            logger.error("❌ [Athena Bridge V2] Athena root not found. Check ATHENA_PATH.")
            return False

        if athena_root not in sys.path:
            sys.path.insert(0, athena_root)
            logger.info("🔗 [Athena Bridge V2] Linked to engine at: %s", athena_root)

        try:
            from visualizers.engine.builder import build_device_figure
            from visualizers.engine.components import (
                DirectorFeature,
                IDEFeature,
                OrganicLayer,
                StructuralLayer,
            )

            self._engine = {
                "StructuralLayer": StructuralLayer,
                "IDEFeature": IDEFeature,
                "DirectorFeature": DirectorFeature,
                "OrganicLayer": OrganicLayer,
                "build_device_figure": build_device_figure
            }
            return True
        except ImportError as e:
            logger.error("❌ [Athena Bridge V2] Failed to import engine components: %s", e)
            return False

    def _resolve_binding(self, val: Any, data_context: Dict[str, Any]) -> Any:
        """
        데이터 바인딩 및 수식을 해석합니다.
          - {{csv.col}}            : CSV 데이터 컨텍스트에서 값 읽기
          - {{csv.col * 1.5}}      : CSV 기반 수식
          - {{solve.param_name}}   : research_params.db에서 파라미터 조회
        """
        if not (isinstance(val, str) and val.startswith("{{") and val.endswith("}}")):
            return val

        expr = val[2:-2].strip()

        # --- solve.param_name 바인딩 ---
        if expr.startswith("solve."):
            return self._resolve_solve_param(expr[6:])

        # --- csv 바인딩 ---
        # 보안: CSV 값을 float으로 강제 변환하여 문자열 주입을 원천 차단합니다.
        # strict=True를 사용하여 NaN/Inf 등 데이터 결함이 주입되는 것을 사전에 방지합니다.
        def replace_var(match):
            col_name = match.group(1)
            raw_val = data_context.get(col_name, 0)
            return repr(_safe_float(raw_val, strict=True))

        expr_replaced = re.sub(r"csv\.([a-zA-Z0-9_]+)", replace_var, expr)

        try:
            # 치환 후 표현식은 float 리터럴과 연산자만 포함해야 합니다.
            if not re.match(r"^[0-9eE\+\-\*\/\.\(\)\s]+$", expr_replaced):
                return _safe_float(data_context.get(expr.replace("csv.", ""), val), strict=True)

            result = eval(expr_replaced, {"__builtins__": {}}, {})  # noqa: S307
            return result
        except Exception as exc:
            # Zenith 마감: NaN/Inf 등의 데이터 결함을 0.0으로 뭉개지 않고 에러를 전파하거나 로그를 남깁니다.
            if "invalid numeric" in str(exc).lower():
                logger.warning("⚠️ [Athena Bridge V2] Data Quality Issue: %s", exc)
            return _safe_float(data_context.get(expr.replace("csv.", ""), val), strict=False)

    def _resolve_solve_param(self, param_name: str) -> str:
        """research_params.db에서 가장 최근의 파라미터 값을 조회합니다."""
        athena_root = self._find_athena_root()
        if not athena_root:
            return f"[solve.{param_name}: Athena not found]"

        db_path = os.path.join(athena_root, "research_params.db")
        if not os.path.exists(db_path):
            return f"[solve.{param_name}: DB not found]"

        try:
            import sqlite3
            from contextlib import closing
            # WAL 모드 및 busy_timeout 설정을 통한 동시성 안정성 확보 (v3.0 Zenith)
            with closing(sqlite3.connect(db_path, timeout=30.0)) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT value, unit FROM extracted_params "
                    "WHERE param_name = ? ORDER BY extracted_at DESC LIMIT 1",
                    (param_name,),
                ).fetchone()

            if row is None:
                return f"[solve.{param_name}: not found]"
            value, unit = row["value"], row["unit"]
            return f"{value} {unit}".strip()
        except Exception as exc:
            return f"[solve.{param_name}: error ({exc})]"

    def _map_features(self, layer_spec: Dict[str, Any]) -> Tuple:
        """IDE 및 액정 배향(Director) 등 내부 피처들을 매핑합니다."""
        features = []

        if "ide" in layer_spec:
            spec = layer_spec["ide"]
            features.append(self._engine["IDEFeature"](
                pitch=float(spec.get("pitch", 0.5)),
                width_ratio=float(spec.get("width_ratio", 0.5)),
                orientation=spec.get("orientation", "length"),
                color=spec.get("color", "#f1c40f")
            ))

        if "director" in layer_spec:
            spec = layer_spec["director"]
            features.append(self._engine["DirectorFeature"](
                alignment_type=spec.get("type", "planar"),
                vector_density=int(spec.get("density", 8)),
                color=spec.get("color", "#2c3e50")
            ))

        return tuple(features)

    _CONTEXT_DPI: Dict[str, int] = {"POSTER": 300}

    @staticmethod
    def _read_quality_sidecar(output_path: str) -> Optional[Dict[str, Any]]:
        """output_path 기준으로 프로젝트의 quality_metrics.json 사이드카를 탐색하여 읽습니다."""
        try:
            out = Path(output_path).resolve()
            # results/ 디렉토리를 기준으로 프로젝트 루트를 추론
            for parent in out.parents:
                sidecar = parent / "results" / "diagnostics" / "quality_metrics.json"
                if sidecar.exists():
                    payload = json.loads(sidecar.read_text(encoding="utf-8"))
                    if isinstance(payload, dict) and "quality_passed" in payload:
                        return payload
        except Exception:
            pass
        return None

    @staticmethod
    def _apply_quality_overlay(fig, quality_info: Dict[str, Any]) -> None:
        """quality_passed=False일 때 figure에 블러 효과와 경고 오버레이를 적용합니다."""
        try:
            from matplotlib.patches import FancyBboxPatch
        except ImportError:
            # Fallback if matplotlib patches are restricted or missing
            return

        warnings = quality_info.get("cv_warnings", [])

        # 1. 모든 Axes에 반투명 블러 레이어 추가
        for ax in fig.get_axes():
            bbox = ax.get_position()
            blur_patch = FancyBboxPatch(
                (bbox.x0, bbox.y0), bbox.width, bbox.height,
                boxstyle="square,pad=0",
                facecolor="white", alpha=0.35, edgecolor="none",
                transform=fig.transFigure, zorder=999,
            )
            fig.patches.append(blur_patch)

        # 2. 대각선 경고 워터마크
        fig.text(
            0.5, 0.5, "⚠ DATA QUALITY WARNING",
            fontsize=18, color="#d35400", alpha=0.45,
            ha="center", va="center", rotation=30,
            transform=fig.transFigure, zorder=1000,
            fontweight="bold",
        )

        # 3. 하단에 CV 상세 정보 표시
        if warnings:
            detail_parts = [f"{w['column']}(CV={w['cv']:.1%})" for w in warnings[:4]]
            detail = "High noise: " + ", ".join(detail_parts)
            if len(warnings) > 4:
                detail += f" +{len(warnings) - 4} more"
            fig.text(
                0.5, 0.02, detail,
                fontsize=8, color="#7f8c8d", alpha=0.8,
                ha="center", va="bottom",
                transform=fig.transFigure, zorder=1000,
            )

    def _resolve_context(self, spec: Dict[str, Any]) -> str:
        """Derive CONTEXT_STYLES key from spec or THEME_FORMAT env var."""
        raw = spec.get("target_format") or os.environ.get("THEME_FORMAT", "nature")
        return str(raw).upper()

    def _write_manifest(self, output_path: str, manifest: RenderManifest) -> str:
        """Write render manifest JSON sidecar next to the artifact."""
        manifest_path = os.path.splitext(output_path)[0] + '.manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return manifest_path

    def render(self, spec: Dict[str, Any], output_path: str, data_context: Optional[Dict] = None) -> bool:
        """Full-Feature 매핑을 통해 고품질 도식을 렌더링합니다."""
        if not self.load_engine():
            return False

        data_context = data_context or {}
        context = self._resolve_context(spec)

        # Apply journal typography (font family + mathtext) so Hub-triggered Athena
        # diagrams share the same Arial/mathtext stack as Hub data plots.
        save_func = None
        try:
            from themes.journal_theme import apply_journal_theme, save_journal_fig
            theme_format = os.environ.get("THEME_FORMAT", "nature").lower()
            font_scale = float(os.environ.get("THEME_SCALE", "1.0"))
            apply_journal_theme(target_format=theme_format, font_scale=font_scale)
            save_func = save_journal_fig
        except Exception:
            pass  # non-fatal: engine renders with current rcParams
        dpi = spec.get("dpi") or self._CONTEXT_DPI.get(context, 600)

        fig = None
        try:
            layers = []
            for l_spec in spec.get("layers", []):
                thickness = self._resolve_binding(l_spec.get("thickness", 0.5), data_context)
                bending = self._resolve_binding(l_spec.get("bending_angle", 0.0), data_context)
                alpha = float(l_spec.get("alpha", 1.0))
                z_offset = float(l_spec.get("z_offset", 0.0))

                layers.append(self._engine["StructuralLayer"](
                    name=l_spec.get("name", "Layer"),
                    material=l_spec.get("material", "default"),
                    thickness=float(thickness),
                    width=float(l_spec.get("width", 4.0)),
                    length=float(l_spec.get("length", 2.2)),
                    color_override=l_spec.get("color", ""),
                    alpha=alpha,
                    z_offset=z_offset,
                    bending_angle=float(bending),
                    visible=bool(l_spec.get("visible", True)),
                    internal_features=self._map_features(l_spec)
                ))

            fig, ax, meta = self._engine["build_device_figure"](
                title=spec.get("title", "Athena-Hub V2 Render"),
                layers=layers,
                view_mode=spec.get("view_mode", "isometric"),
                context=context,
            )

            # Quality-aware 시각 피드백: 사이드카에서 품질 결과를 읽어 동적 오버레이 적용
            quality_info = self._read_quality_sidecar(output_path)
            if quality_info and not quality_info.get("quality_passed", True):
                self._apply_quality_overlay(fig, quality_info)
                logger.warning(
                    "⚠️ [Athena Bridge V2] Quality overlay applied — "
                    "%s column(s) exceeded CV threshold",
                    len(quality_info.get("cv_warnings", [])),
                )

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            if save_func:
                save_func(fig, output_path, dpi=dpi)
            else:
                fig.savefig(output_path, dpi=dpi, bbox_inches='tight')

            # Write manifest sidecar for assembly pipeline
            fig_w_inch, fig_h_inch = fig.get_size_inches()
            manifest: RenderManifest = {
                'artifact_path': os.path.abspath(output_path),
                'artifact_format': os.path.splitext(output_path)[1].lstrip('.').lower(),
                'width_mm': fig_w_inch * 25.4,
                'height_mm': fig_h_inch * 25.4,
                'dpi': dpi,
                'layers': len(layers),
                'view_mode': spec.get('view_mode', 'isometric'),
                'context': context,
                'font_strategy': 'compensate',
                'source': 'athena_bridge_v2',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            manifest_path = self._write_manifest(output_path, manifest)

            manifest_name = os.path.basename(manifest_path)
            logger.info(
                "✅ [Athena Bridge V2] Rendered: %s "
                "(Layers: %s, context: %s, dpi: %s, manifest: %s)",
                os.path.basename(output_path),
                len(layers),
                context,
                dpi,
                manifest_name,
            )
            return True

        except Exception as e:
            logger.exception("❌ [Athena Bridge V2] Render failed: %s", e)
            return False
        finally:
            if fig is not None:
                plt.close(fig)

def _safe_float(val: Any, strict: bool = False) -> float:
    """값을 float으로 안전하게 변환합니다.
    strict=True일 경우 NaN/Inf 발생 시 ValueError를 발생시켜 데이터 결함을 알립니다.
    """
    try:
        f_val = float(val)
        if strict and (math.isnan(f_val) or math.isinf(f_val)):
            raise ValueError(f"Invalid numeric value (NaN/Inf) detected: {val}")
        return f_val
    except (TypeError, ValueError) as exc:
        if strict:
            raise ValueError(f"Failed to convert to float: {val} ({exc})") from exc
        return 0.0


bridge = AthenaBridge()

def render_from_athena_spec(spec: Dict[str, Any], output_path: str, data_context: Optional[Dict] = None):
    return bridge.render(spec, output_path, data_context)
